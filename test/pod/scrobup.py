"""The scrobble upload (patch/scrobup.c, docs/modules/scrobble.md "Upload"): the log's lines in batches to ListenBrainz (the request, its JSON, the token's header),
the lines that are skipped, what a failure leaves (401, 500, 429, a timeout, no connection), the archive and the one rewrite of the log, a listen appended while the
upload runs, a card that does not take the archive or the new log, and when no upload starts; a batch answered 400 sent again one listen a request (only the listens refused alone go to
.scrobbler.log.rejected), the kill switch between requests; who started a job (the settings pages or the automatic upload) and Invalid Token; the account (the token and the user name in the card's scrobble.ini and nowhere else: how the file is read, its in-place rewrite that keeps every other byte, validate-token writing USER back, a file over the cap, no card). The compiled payload runs under Unicorn; the thread's routine is run by the
test (pthread_create is recorded), libcurl is the harness's scripted server."""
import hashlib
import json
import os
import urllib.parse

from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

podcasts = sibling('podcasts')
LOG = '/mnt/mmc/.scrobbler.log'
SENT, TMP, REJ = LOG + '.sent', LOG + '.tmp', LOG + '.rejected'
INI = '/mnt/mmc/scrobble.ini'   # patch/scrobup.c SU_INI: the account's only store
INI_TMP = INI + '.tmp'
INI_MAX = O['SU_INI_MAX']
TOKEN = '0f8fad5b-d9cb-469f-a165-70867728950e'
OLD_FLASH, OLD_CARD = '/mnt/data/m1plus/scrobble-listenbrainz', '/mnt/mmc/listenbrainz-token.txt'   # where the account must never be again
URL = 'https://api.listenbrainz.org/1/submit-listens'
CHECK_URL = 'https://api.listenbrainz.org/1/validate-token'
HEADER = '#AUDIOSCROBBLER/1.1\n#TZ/UTC\n#CLIENT/M1+ Music\n'
BATCH, LINE, RAW, BODY, WIN, TOKEN_MAX = O['SU_BATCH'], O['SU_LINE'], O['SU_RAW'], O['SU_BODY'], O['SU_WIN'], O['SU_TOKEN']
NAME_MAX, ANS, REJ_MAX = O['SU_NAME'], O['SU_ANS'], O['SU_REJ']
OK, FAIL, AUTH, DISK = 1, -1, -2, -3   # patch/scrobup.h SCROBUP_*
UPLOAD, CHECK = 0, 1                  # scrobup_kind
UI, AUTO = 0, 1                       # scrobup_owner: patch/scrobup.h SCROBUP_UI, SCROBUP_AUTO
T0 = 1800000000
KILL = '/mnt/mmc/m1plus-off'


def s32(v): return v - (1 << 32) if v & 0x80000000 else v


def line(i=0, artist='Miles Davis', album='Kind of Blue', title=None, track='2', ln='300', rating='L', stamp=None, tail='\t\n'):
    return f'{artist}\t{album}\t{f"Track {i}" if title is None else title}\t{track}\t{ln}\t{rating}\t{T0 + i if stamp is None else stamp}{tail}'


def listen(i=0, artist='Miles Davis', album='Kind of Blue', title=None, track=2, ln=300, stamp=None):
    """The payload item of line(i)."""
    info = {'duration': ln, 'tracknumber': track, 'media_player': 'M1+ Music', 'submission_client': 'M1+ Music'}
    meta = {'artist_name': artist, 'track_name': f'Track {i}' if title is None else title, 'release_name': album, 'additional_info': {k: v for k, v in info.items() if v}}
    return {'listened_at': T0 + i if stamp is None else stamp, 'track_metadata': {k: v for k, v in meta.items() if v}}


class Site:
    """The scripted service: every request (url, header lines, body, its JSON, libcurl's options) is kept; the answers are `answers` in order (the last repeats; none: 200),
    or what answers(request) returns (judge).
    during(k) runs while request k (from 1) is on the wire. held: the log's lock depth at each request."""
    def __init__(self, m, answers=None, during=None):
        self.m, self.answers, self.during, self.reqs, self.held = m, answers or [{}], during, [], []

    def __call__(self, url, o):
        m = self.m
        body = bytes(m.u.mem_read(o[10015], o[60])) if 10015 in o else None   # CURLOPT_POSTFIELDS, CURLOPT_POSTFIELDSIZE (a GET has neither)
        heads, p = [], o.get(10023, 0)   # CURLOPT_HTTPHEADER: a curl_slist {data, next}
        while p:
            heads.append(m.read_cstr(m.word(p))); p = m.word(p + 4)
        form = 'Content-Type: application/x-www-form-urlencoded' in heads   # Last.fm: the decoded (name, value) pairs in the body's order (strict: ASCII only in the body, well-formed UTF-8 behind the escapes, name=value everywhere)
        self.reqs.append({'url': url, 'heads': heads, 'body': body, 'json': json.loads(body.decode('utf-8')) if body is not None and not form else None,   # (strict: well-formed UTF-8, no raw control character)
                          'form': urllib.parse.parse_qsl(body.decode('ascii'), keep_blank_values=True, strict_parsing=True, encoding='utf-8', errors='strict') if form else None, 'o': dict(o)})
        self.held.append(sum({'lock': 1, 'unlock': -1}.get(c[0], 0) for c in m.calls if len(c) == 2 and c[1] == PSYMS['sc_mutex']))
        if self.during: self.during(len(self.reqs))
        if callable(self.answers): return self.answers(self.reqs[-1])
        return self.answers[min(len(self.reqs), len(self.answers)) - 1]

    def listens(self):
        return [x for r in self.reqs if r['json'] for x in r['json']['payload']]


def ini(token=TOKEN, name=None, eol='\n'):
    """The card's scrobble.ini as the payload writes it: the section, TOKEN and, with a confirmed user name, USER."""
    return f'[LISTENBRAINZ]{eol}TOKEN={token}{eol}' + (f'USER={name}{eol}' if name else '')


def machine(log=None, token=TOKEN, answers=None, during=None, name=None, raw=None):
    """token / name: the account in the card's scrobble.ini (token None: no file); raw: the file's bytes as a user wrote them."""
    m = podcasts.PM()
    m.wall = T0 + 100000
    if raw is not None: m.fs[INI] = raw if isinstance(raw, bytes) else raw.encode()
    elif token is not None: m.fs[INI] = ini(token, name).encode()
    if log is not None: m.fs[LOG] = log if isinstance(log, bytes) else log.encode()
    m.site = m.curl_site = Site(m, answers, during)
    m.log = []
    return m


def call(m, fn, **kw):
    """One call of the payload; its mocked calls are added to m.log (m.calls holds one call's only)."""
    r = m.call(fn, **kw)
    m.log += m.calls
    return r


def names(m): return [c[0] for c in m.log]


def start(m, owner=UI):
    m.thread = None
    return s32(call(m, PSYMS['scrobup_start'], a0=owner, count=1 << 30))


def busy(m): return call(m, PSYMS['scrobup_busy'], count=10000)


def poll(m, p=None):
    p = m.alloc(4) if p is None else p
    if p: m.setword(p, 0xdead)
    return s32(call(m, PSYMS['scrobup_poll'], a0=p, count=1 << 30)), m.word(p) if p else None


def work(m): call(m, m.thread[0], a0=m.thread[1], count=1 << 40)


def upload(m, owner=UI):
    """A whole upload: (result, sent)."""
    r = start(m, owner)
    assert r == 1 and m.thread, r
    work(m)
    return poll(m)


def log_of(m): return m.fs.get(LOG, b'').decode('utf-8', 'replace') if LOG in m.fs else None
def sent_of(m): return m.fs.get(SENT, b'').decode('utf-8', 'replace') if SENT in m.fs else None
def wrote(m): return [c for c in m.log if c[0] in ('write', 'rename', 'unlink') or (c[0] == 'open' and c[2] & 3)]


def upload_tests(ctx):
    """Two batches: the request, the JSON and its escaping, the archive, the log's one rewrite, the poll."""
    expect = ctx.expect
    expect((BATCH, LINE, RAW, BODY, WIN, TOKEN_MAX) == (50, 2560, 16384, 196608, 65536, 128), 'the limits: 50 listens a request, lines up to 2560 bytes, 16 KB of log a request in a 192 KB body, 64 KB windows, a token up to 128 bytes')
    expect(RAW * 6 + BATCH * 280 < BODY and LINE < RAW and LINE < WIN, 'a batch\'s body fits whatever the escaping (6 bytes a byte, under 280 bytes of JSON a listen), and a line fits a batch and a window')
    odd = [line(2, artist='AC/DC "Live"', title='Back\\Slash'), line(3, artist='坂本龍一', album='千のナイフ', title='東風'), line(4, album='', track='', title='No album'),
           line(5, title='Bell\x07 and\x1f unit'), line(6, track='0', ln='0', title='Zeros')]
    lines = [line(0), line(1)] + odd + [line(i) for i in range(7, 60)]
    raw = (HEADER + ''.join(lines)).encode() + b'Caf\xe9 Bad\tAlbum\t\xff\xfe title\t1\t200\tL\t1800000500\t\n'   # Latin-1 bytes, not UTF-8
    m = machine(raw)
    expect(poll(m) == (0, 0xdead) and busy(m) == 0, 'idle: the poll returns 0 and leaves the count alone')
    expect(start(m) == 1 and m.thread and busy(m) == 1 and 'pthread_create' in names(m), 'a start: 1, one thread, busy')
    expect(not wrote(m) and 'curl_easy_perform' not in names(m) and not m.site.reqs, 'the start itself writes nothing and asks the network nothing')
    th = m.thread
    expect(start(m) == 0 and m.thread is None and poll(m) == (0, 0xdead), 'a second start while it runs: 0, no second thread; the poll: 0, still running')
    m.thread = th; m.log = []; work(m)
    expect(start(m) == 0 and busy(m) == 1, 'over but not polled yet: still no second start')
    res = poll(m)
    expect(res == (OK, 61) and 'pthread_join' in names(m) and busy(m) == 0, f'the poll once it is over: done, 61 listens, the thread joined ({res})')
    expect(poll(m) == (0, 0xdead), 'the result is given once')
    q = m.site.reqs
    expect([len(r['json']['payload']) for r in q] == [50, 11], f'two requests: 50 listens, then the other 11 ({[len(r["json"]["payload"]) for r in q]})')
    expect(all(r['url'] == URL and r['heads'] == ['Authorization: Token ' + TOKEN, 'Content-Type: application/json'] for r in q), f'each a POST to submit-listens with the token (the file\'s newline dropped) and the JSON type ({q[0]["url"]}, {q[0]["heads"]})')
    o = q[0]['o']
    expect(o[10065] == '/etc/m1plus-cacert.pem' and o[64] == 1 and o[81] == 2 and o[181] == 2 and 52 not in o, 'TLS: the firmware\'s CA bundle, peer and host verified, HTTPS only, no redirect followed')
    expect(o[78] == O['SU_CONNECT_S'] == 15 and o[13] == O['SU_TOTAL_S'] == 60 and o[99] == 1 and o[20011], 'bounded: 15 s to connect, 60 s in all, no signals (a worker thread), the answer\'s body taken by a callback')
    expect(m.site.held == [0, 0], f'no request is made with the log\'s lock held ({m.site.held})')
    expect(all(r['json']['listen_type'] == 'import' and set(r['json']) == {'listen_type', 'payload'} for r in q), 'listen_type import')
    p = m.site.listens()
    expect(p[0] == {'listened_at': T0, 'track_metadata': {'artist_name': 'Miles Davis', 'track_name': 'Track 0', 'release_name': 'Kind of Blue', 'additional_info': {'duration': 300, 'tracknumber': 2, 'media_player': 'M1+ Music', 'submission_client': 'M1+ Music'}}}, f'a listen: the time a number, artist, title, album, the length and the track number as numbers, the player and the client ({p[0]})')
    expect(p[2] == listen(2, artist='AC/DC "Live"', title='Back\\Slash') and rb'AC/DC \"Live\"' in q[0]['body'] and rb'Back\\Slash' in q[0]['body'], f'a quote and a backslash are escaped ({p[2]})')
    expect(p[3] == listen(3, artist='坂本龍一', album='千のナイフ', title='東風') and '坂本龍一'.encode() in q[0]['body'], f'CJK goes as its UTF-8 bytes ({p[3]})')
    expect(p[4] == listen(4, album='', track=0, title='No album') and 'release_name' not in p[4]['track_metadata'] and 'tracknumber' not in p[4]['track_metadata']['additional_info'], f'no album, no track number: neither key ({p[4]})')
    expect(p[5] == listen(5, title='Bell\x07 and\x1f unit') and rb'Bell\u0007 and\u001f unit' in q[0]['body'], f'control bytes as \\u00XX ({p[5]})')
    expect(p[6] == listen(6, track=0, ln=0, title='Zeros'), f'a length and a track number of 0 are left out ({p[6]})')
    expect(p[60] == listen(artist='Caf� Bad', album='Album', title='�� title', track=1, ln=200, stamp=1800000500), f'bytes that are not UTF-8 go as U+FFFD: the request stays valid ({p[60]})')
    expect(p[7:60] == [listen(i) for i in range(7, 60)], 'the rest in the log\'s order')
    expect(m.fs[LOG] == HEADER.encode() and m.fs[SENT] == raw[len(HEADER):] and TMP not in m.fs, f'afterwards: the log is its header, the 61 lines are in .scrobbler.log.sent as they were (no header), no temp file ({m.fs[LOG]!r})')
    steps = [c for c in m.log if c[0] in ('rename', 'curl_perform', 'fsync')]
    expect([c[0] for c in steps].count('rename') == 1 and steps[-1] == ('rename', TMP, LOG) and ('fsync', SENT) in steps and steps.index(('fsync', SENT)) > max(i for i, c in enumerate(steps) if c[0] == 'curl_perform'),
           f'the log is rewritten once, after the last request, and renamed only after the archive is synced ({[c[0] for c in steps]})')
    locks = [c[0] for c in m.log if len(c) == 2 and c[1] == PSYMS['sc_mutex']]
    expect(locks == ['lock', 'unlock'] * (len(locks) // 2) and len(locks) == 4, f'the lock: once for the read of the log, once for the rewrite ({locks})')
    i0, i1 = [i for i, c in enumerate(m.log) if c == ('lock', PSYMS['sc_mutex'])][1], [i for i, c in enumerate(m.log) if c == ('unlock', PSYMS['sc_mutex'])][1]
    expect(all(i0 < i < i1 for i, c in enumerate(m.log) if c[0] in ('write', 'rename') or (c[0] == 'open' and c[1] in (LOG, SENT, TMP) and i > i0)), 'the archive and the rewrite are inside it')
    # again: nothing left
    m.log = []; n = len(m.site.reqs)
    expect(upload(m) == (OK, 0) and len(m.site.reqs) == n and not wrote(m), 'an upload right after: nothing to upload, no request, nothing written')
    # the archive grows
    m.fs[LOG] += line(70).encode()
    expect(upload(m) == (OK, 1) and m.fs[SENT] == raw[len(HEADER):] + line(70).encode() and m.fs[LOG] == HEADER.encode(), 'the next listen is appended to the archive')
    # exactly one batch, and one more
    m = machine(HEADER + ''.join(line(i) for i in range(BATCH)))
    expect(upload(m) == (OK, BATCH) and len(m.site.reqs) == 1, '50 lines: one request')
    m = machine(HEADER + ''.join(line(i) for i in range(BATCH + 1)))
    expect(upload(m) == (OK, BATCH + 1) and [len(r['json']['payload']) for r in m.site.reqs] == [BATCH, 1], '51: two')
    # the switch gates logging only
    m = machine(HEADER + line(0)); m.fs['/mnt/data/m1plus/scrobbling'] = b'0\n'
    expect(upload(m) == (OK, 1), 'with Scrobbling off a log that is there is still uploaded')


def skip_tests(ctx):
    """Lines that are not sent leave the log with the sent ones; comments are not archived."""
    expect = ctx.expect
    junk = ['x' * (LINE + 1) + '\n', line(1, rating='S'), line(2, artist=''), line(3, title=''), line(4, stamp='18000x0000'), line(5, stamp='18000000000'), line(6, stamp='0'), line(7, stamp=''),
            line(8, stamp='1033430399'), 'Artist\tAlbum\tTitle\t1\t200\tL\n', 'just some text\n', '\n', line(9, stamp='4294967296')]
    good = [line(20), line(21, tail='\t\r\n'), line(23, tail='\n'), line(24, stamp='1033430400'), line(25, ln='abc', track='A1'), line(26, artist='y' * (LINE + 1 - len(line(26, artist='')))), line(27, tail='\tmbid-0001\n')]
    text = HEADER + good[0] + '# a comment\n' + ''.join(junk) + ''.join(good[1:]) + '#another\n' + 'Cut\tAlbum\tHalf a li'
    m = machine(text)
    res = upload(m); p = m.site.listens()
    expect(res == (OK, len(good)) and len(m.site.reqs) == 1, f'the over-long line, the ones not rated L, without artist or title, with a time that is not 1 to 10 digits, 0, before October 2002 or past 32 bits, with too few fields: not sent ({res})')
    expect([x['listened_at'] for x in p] == [T0 + 20, T0 + 21, T0 + 23, 1033430400, T0 + 25, T0 + 26, T0 + 27], f'sent: a CRLF line, a line without the last tab, the first second ListenBrainz takes, a line of exactly the longest length ({[x["listened_at"] for x in p]})')
    expect(p[4]['track_metadata']['additional_info'] == {'media_player': 'M1+ Music', 'submission_client': 'M1+ Music'} and len(good[5]) == LINE + 1 and p[5]['track_metadata']['artist_name'] == 'y' * (LINE + 1 - len(line(26, artist=''))), f'a length or a track number that is no number is left out ({p[4]})')
    expect(log_of(m) == HEADER + 'Cut\tAlbum\tHalf a li', f'the log keeps only its header and the line that has no end yet ({log_of(m)!r})')
    expect(sent_of(m) == good[0] + ''.join(junk) + ''.join(good[1:]), 'the archive has every line that left, skipped ones too, and no comment')
    # junk only
    m = machine(HEADER + ''.join(junk))
    expect(upload(m) == (OK, 0) and not m.site.reqs and log_of(m) == HEADER and sent_of(m) == ''.join(junk), 'a log of skipped lines only: no request, and they leave (one bad line never blocks an upload)')
    # skipped lines before a failed batch stay
    m = machine(HEADER + junk[1] + line(0), answers=[{'code': 500}])
    expect(upload(m) == (FAIL, 0) and log_of(m) == HEADER + junk[1] + line(0) and SENT not in m.fs, 'nothing leaves when the first batch fails')
    # a line longer than a window, and a log of several windows
    lines = [line(i) for i in range(900)]
    big = 'z' * (2 * WIN) + '\n'
    text = HEADER + ''.join(lines[:800]) + big + ''.join(lines[800:])
    expect(len(HEADER + ''.join(lines[:800])) < WIN and 2 * WIN < len(HEADER + ''.join(lines[:800]) + big) < 3 * WIN, 'the long line begins in the first window and ends in the third')
    m = machine(text)
    res = upload(m)
    expect(res == (OK, 900) and [x['listened_at'] for x in m.site.listens()] == [T0 + i for i in range(900)] and [len(r['json']['payload']) for r in m.site.reqs] == [BATCH] * 18,
           f'three windows: every listen once, in order, in full batches across the windows\' ends; the long line is skipped whole ({res}, {len(m.site.reqs)})')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines[:800]) + big + ''.join(lines[800:]) and [c[0] for c in m.log].count('rename') == 1, 'one rewrite for the whole log')
    expect(m.site.held == [0] * 18, 'no request under the lock')
    # the body's bound: long lines of control bytes (6 bytes each in JSON)
    fat = [line(i, title='\x01' * 2000) for i in range(20)]
    m = machine(HEADER + ''.join(fat))
    res = upload(m)
    per = RAW // (len(fat[0]))
    expect(res == (OK, 20) and [len(r['json']['payload']) for r in m.site.reqs] == [per, per, 20 - 2 * per] and max(len(r['body']) for r in m.site.reqs) < BODY and m.site.listens()[0]['track_metadata']['track_name'] == '\x01' * 2000,
           f'a batch holds at most 16 KB of the log, so its body fits ({res}, {[len(r["body"]) for r in m.site.reqs]})')
    # an over-long line without an end, at the log's end
    m = machine(HEADER + line(0) + 'w' * (LINE + 1))
    expect(upload(m) == (OK, 1) and log_of(m) == HEADER and sent_of(m) == line(0) + 'w' * (LINE + 1) + '\n', 'an endless over-long tail leaves too, closed with a newline in the archive')


def nothing_tests(ctx):
    """No log, an empty log, a header only: done, nothing sent, nothing written."""
    expect = ctx.expect
    for what, log in (('no log', None), ('an empty log', ''), ('a header only', HEADER), ('comments only', HEADER + '# one\n#two\n')):
        m = machine(log); m.log = []
        res = upload(m)
        expect(res == (OK, 0) and not m.site.reqs and 'curl_easy_init' not in names(m), f'{what}: nothing to upload, no request ({res})')
        expect(not wrote(m) and log_of(m) == log and SENT not in m.fs and TMP not in m.fs, f'{what}: nothing is written (the log is not made, not rewritten)')
        expect([c[0] for c in m.log if len(c) == 2 and c[1] == PSYMS['sc_mutex']] == ['lock', 'unlock'], f'{what}: the lock is taken for the one read and given back')


def fail_tests(ctx):
    """The first failure ends the upload; what was sent before it leaves the log, the rest stays."""
    expect = ctx.expect
    lines = [line(i) for i in range(60)]
    text = HEADER + ''.join(lines)
    for what, ans, want in (('401', {'code': 401}, AUTH), ('500', {'code': 500}, FAIL), ('429', {'code': 429}, FAIL), ('503', {'code': 503}, FAIL), ('204', {'code': 204}, FAIL),
                            ('a timeout', {'rc': 28, 'code': 0}, FAIL), ('no connection', {'rc': 7, 'code': 0}, FAIL), ('a certificate that does not verify', {'rc': 60, 'code': 0}, FAIL),
                            ('a transfer that broke after a 200 header', {'rc': 56, 'code': 200}, FAIL)):
        m = machine(text, answers=[ans]); m.log = []
        res = upload(m)
        expect(res == (want, 0) and len(m.site.reqs) == 1, f'{what} on the first request: {want}, 0 sent, no second request ({res}, {len(m.site.reqs)})')
        expect(log_of(m) == text and SENT not in m.fs and TMP not in m.fs and not wrote(m), f'{what}: the log is untouched, nothing archived')
        expect('pthread_join' in names(m) and busy(m) == 0 and 'curl_easy_cleanup' in names(m), f'{what}: the thread is joined, the handle freed')
    for what, ans, want in (('500', {'code': 500}, FAIL), ('401', {'code': 401}, AUTH), ('a timeout', {'rc': 28, 'code': 0}, FAIL)):
        m = machine(text, answers=[{}, ans])
        res = upload(m)
        expect(res == (want, 50) and len(m.site.reqs) == 2, f'{what} on the second request: {want} with the 50 listens the first one sent ({res})')
        expect(log_of(m) == HEADER + ''.join(lines[50:]) and sent_of(m) == ''.join(lines[:50]) and TMP not in m.fs, f'{what}: the 50 sent are archived, the log keeps the header and the other 10')
        m.site.answers = [{}]
        res = upload(m)
        expect(res == (OK, 10) and [x['listened_at'] for x in m.site.reqs[-1]['json']['payload']] == [T0 + i for i in range(50, 60)] and log_of(m) == HEADER and sent_of(m) == ''.join(lines),
               f'{what}: the next upload sends the 10 that stayed, once ({res})')
    # no memory
    for size in (WIN, RAW, BODY):
        m = machine(text); m.calloc_fail_size = size
        res = upload(m)
        expect(res == (FAIL, 0) and log_of(m) == text and not m.site.reqs and SENT not in m.fs, f'no memory in the thread ({size} bytes): a failure, nothing sent or written ({res})')
    m = machine(text); m.calloc_fail = True
    expect(start(m) == -1 and busy(m) == 0, 'no memory to read the token with: no start')
    m = machine(text); m.thread_ok = False
    expect(start(m) == -1 and busy(m) == 0 and poll(m) == (0, 0xdead), 'no thread: -1, not busy')
    m.thread_ok = True
    expect(upload(m) == (OK, 60), 'and it starts when one can be made')


def append_tests(ctx):
    """The log's lock: a listen appended while the upload runs is kept; the appender takes the same lock."""
    expect = ctx.expect
    lines = [line(i) for i in range(60)]
    text = HEADER + ''.join(lines)
    extra = line(99, title='Appended meanwhile')
    for k in (1, 2):
        def during(i, k=k):
            if i == k: m.fs[LOG] += extra.encode()
        m = machine(text, during=during)
        res = upload(m)
        expect(res == (OK, 60) and log_of(m) == HEADER + extra and sent_of(m) == ''.join(lines), f'a listen appended during request {k}: it stays in the log, after the header, and is not archived ({res}, {log_of(m)!r})')
        expect(upload(m) == (OK, 1) and m.site.listens()[-1] == listen(99, title='Appended meanwhile') and log_of(m) == HEADER, 'and goes with the next upload')
    def during(i):
        if i == 1: m.fs[LOG] += extra.encode()
    m = machine(text, answers=[{}, {'code': 500}], during=during)
    expect(upload(m) == (FAIL, 50) and log_of(m) == HEADER + ''.join(lines[50:]) + extra, 'with a failed second batch: the unsent lines and the new one stay, in order')
    def during(i):
        if i == 1: m.fs[LOG] += extra.encode()[:20]
        if i == 2: m.fs[LOG] += extra.encode()[20:]
    m = machine(HEADER + ''.join(lines[:50]) + line(50), during=during)
    expect(upload(m) == (OK, 51) and log_of(m) == HEADER + extra, 'bytes that arrive after the last window was read are never part of what leaves')
    # the appender (patch/scrobble.c) under the same lock
    sc = sibling('scrobble')

    def played(m, r):
        """152 s of the track, a look a second: every look's mocked calls."""
        m.log = []
        for p in range(1, 153):
            sc.note(m, r, p, 300, 1000); m.log += m.calls
    m = sc.machine(); r = sc.song(m); sc.note(m, r, 0, 300)
    played(m, r)
    io = [c for c in m.log if (c[0] in ('open', 'write', 'fsync', 'close') and c[1] == LOG) or (len(c) == 2 and c[1] == PSYMS['sc_mutex'])]
    expect([c[0] for c in io] == ['lock', 'open', 'write', 'fsync', 'close', 'unlock'] and len(sc.lines(m)) == 1, f'the append of a listen: lock, open, write, fsync, close, unlock ({[c[0] for c in io]})')
    m = sc.machine(); r = sc.song(m); sc.note(m, r, 0, 300); m.fail.add(('open', LOG))
    played(m, r)
    locks = [c[0] for c in m.log if len(c) == 2 and c[1] == PSYMS['sc_mutex']]
    expect(len(locks) == 6 and locks == ['lock', 'unlock'] * 3, f'a log that does not open: tried at each look from the 150th second, the lock given back each time ({locks[:8]})')
    m = sc.machine(); r = sc.song(m); sc.note(m, r, 0, 300); m.card_mounted = False
    played(m, r)
    expect(not [c for c in m.log if len(c) == 2 and c[1] == PSYMS['sc_mutex']], 'no card: the lock is not taken at all')


def disk_tests(ctx):
    """The card does not take the archive or the new log: the log stays as it was."""
    expect = ctx.expect
    lines = [line(i) for i in range(60)]
    text = HEADER + ''.join(lines)
    for what, fail, arc in (('the archive is not written', ('write', SENT), ''), ('the archive does not open', ('open', SENT), None), ('the archive does not sync', ('fsync', SENT), ''.join(lines)),
                            ('the new log is not written (a full card)', ('write', TMP), None), ('the new log does not open', ('open', TMP), None), ('the new log does not sync', ('fsync', TMP), None),
                            ('the rename fails', ('rename', LOG), ''.join(lines)), ('the log does not read', ('read', LOG), None)):
        m = machine(text); m.fail.add(fail)
        if fail == ('read', LOG):   # (the windows read; the rewrite does not)
            m.fail.discard(fail); m.site.during = lambda i, m=m, fail=fail: m.fail.add(fail) if i == 2 else None
        res = upload(m)
        expect(res == (DISK, 60) and len(m.site.reqs) == 2, f'{what}: a storage failure, with the 60 the service took ({res})')
        expect(log_of(m) == text and TMP not in m.fs, f'{what}: the log is as it was, no temp file left ({log_of(m)[-40:]!r})')
        expect(sent_of(m) == arc, f'{what}: the archive {"is not made" if arc is None else "has " + str(arc.count(chr(10))) + " lines"} ({None if sent_of(m) is None else len(sent_of(m))})')
        m.fail.discard(fail); m.site.during = None
        res = upload(m)
        expect(res == (OK, 60) and log_of(m) == HEADER and sent_of(m) == (arc or '') + ''.join(lines), f'{what}: the next upload sends them again and retires them ({res})')
    # the card goes away
    def during(i):
        if i == 1: m.card_mounted = False
    m = machine(text, during=during); m.log = []
    res = upload(m)
    expect(res == (DISK, 60) and not wrote(m) and len(m.site.reqs) == 2 and not [c for c in m.log[[i for i, c in enumerate(m.log) if c[0] == 'curl_perform'][0]:] if c[0] == 'open'], f'the card is unmounted during a request: nothing more is opened or written under its mount point ({res})')
    m = machine(text); m.fs[LOG] = text.encode()
    def during(i):
        if i == 2: m.fs[LOG] = HEADER.encode()   # (a computer changed the card's log in between)
    m.site.during = during
    res = upload(m)
    expect(res == (DISK, 60) and log_of(m) == HEADER and SENT not in m.fs and TMP not in m.fs, f'a log shorter than what was read: left alone ({res})')
    # the log is another one when the upload comes back to it
    other = [line(i, artist='John Coltrane') for i in range(60)]
    for what, new in (('of the same size', HEADER + ''.join(other)), ('a longer one', HEADER + ''.join(other) + line(99)), ('with one byte changed', text.replace('Kind of Blue', 'Kind of Blux', 1)),
                      ('changed behind the first batch', HEADER + ''.join(lines[:59]) + other[59])):
        for k in (1, 2):
            if k == 1 and 'behind' in what: continue   # (the first request's answer: the second batch is then read from the new log, and sent as it is)
            def during(i, k=k, new=new):
                if i == k: m.fs[LOG] = new.encode()
            m = machine(text, during=during); assert len(new) >= len(text)
            res = upload(m)
            expect(res[0] == DISK and log_of(m) == new and SENT not in m.fs and REJ not in m.fs and TMP not in m.fs, f'the log replaced during request {k}, {what}: a storage failure, none of its lines retired or archived ({res}, {SENT in m.fs})')
            m.site.during = None; m.site.reqs = []
            res = upload(m)
            expect(res[0] == OK and log_of(m) == HEADER and sent_of(m) == new[len(HEADER):] and [l['track_metadata']['artist_name'] for l in m.site.listens()] == [x.split('\t')[0] for x in new[len(HEADER):].splitlines()], f'the log replaced during request {k}, {what}: the next upload sends the new log\'s listens ({res})')
    # a log that is there and does not open or seek is not an empty log
    m = machine(text); m.fail.add(('open', LOG)); m.log = []
    res = upload(m)
    expect(res == (DISK, 0) and not m.site.reqs and not wrote(m) and log_of(m) == text, f'the log is there and does not open: a storage failure, not "nothing to upload" ({res})')
    m.fail.discard(('open', LOG))
    expect(upload(m) == (OK, 60) and log_of(m) == HEADER, 'the log opens again: the 60 go')
    m = machine(None); m.fail.add(('open', LOG)); m.log = []
    res = upload(m)
    expect(res == (DISK, 0) and not m.site.reqs and not wrote(m), f'the open fails for another reason than "no such file" and nothing else finds the log either: a storage failure ({res})')
    def during(i):
        if i == 1: m.fail.add(('read', LOG))
    m = machine(HEADER + ''.join(line(i) for i in range(2000)), during=during)
    res = upload(m)
    expect(res[0] == DISK and log_of(m) == HEADER + ''.join(line(i) for i in range(2000)), f'a read error at the second window: a storage failure, the log as it was ({res})')


def start_tests(ctx):
    """When no upload starts: the token, the card, the kill switch."""
    expect = ctx.expect
    text = HEADER + line(0)
    for what, raw in (('no scrobble.ini', None), ('an empty file', ''), ('white space only', ' \r\n\t\n'), ('the section without a TOKEN line', '[LISTENBRAINZ]\n'), ('an empty TOKEN', '[LISTENBRAINZ]\nTOKEN=\n'),
                      ('a token with a space inside', ini('abc def')), ('a value that is a header', ini('X-Evil: 1')), ('a control byte', ini('abc\x01def')), ('DEL', ini('abc\x7f')), ('a byte past ASCII', ini('abcé')),
                      ('a token of 129 bytes', ini('a' * (TOKEN_MAX + 1))), ('a bare token, no section', TOKEN + '\n'), ('TOKEN outside the section', 'TOKEN=' + TOKEN + '\n[LISTENBRAINZ]\n'),
                      ('TOKEN in another section only', '[LASTFM]\nTOKEN=' + TOKEN + '\n')):
        m = machine(text, token=None, raw=raw); m.log = []
        r = start(m)
        expect(r == -1 and m.thread is None and 'pthread_create' not in names(m) and busy(m) == 0 and not wrote(m), f'{what}: -1, no thread ({r})')
    for what, raw, want in (('the file as the player writes it', ini(), TOKEN), ('CRLF lines', ini(eol='\r\n'), TOKEN), ('no newline at the end', ini()[:-1], TOKEN), ('128 bytes', ini('k' * TOKEN_MAX), 'k' * TOKEN_MAX),
                            ('not a UUID', ini('my-token_01.~'), 'my-token_01.~'), ('a user name beside it', ini(name='rob'), TOKEN), ('a token with = in it', ini('abc=def=='), 'abc=def==')):
        m = machine(text, raw=raw)
        res = upload(m)
        expect(res == (OK, 1) and m.site.reqs[0]['heads'][0] == 'Authorization: Token ' + want, f'{what}: sent as "Token {want[:12]}..." ({res})')
    m = machine(text); m.card_mounted = False; m.log = []
    expect(start(m) == -1 and 'pthread_create' not in names(m) and not [c for c in m.log if c[0] == 'open' and c[1].startswith('/mnt/mmc')], 'no mounted card: -1, the mount point is not opened')
    for kill in (KILL, '/mnt/data/m1plus-off'):
        m = machine(text); m.present.add(kill); m.log = []
        expect(start(m) == -1 and 'pthread_create' not in names(m) and 'curl_global_init' not in names(m) and INI not in [c[1] for c in m.log if c[0] == 'open'], f'the kill switch ({kill}): -1, nothing read')
        m.present.discard(kill)
        expect(upload(m) == (OK, 1), 'without it the same machine uploads')
    # the token is read at each start: a file changed on a computer needs no reboot
    m = machine(text, token='first')
    expect(upload(m) == (OK, 1) and account(m) == (1, b''), 'an upload with one token')
    m.fs[INI] = ini('second').encode(); m.fs[LOG] += line(1).encode()
    expect(upload(m) == (OK, 1) and [r['heads'][0] for r in m.site.reqs] == ['Authorization: Token first', 'Authorization: Token second'], 'a changed scrobble.ini is used by the next start')
    del m.fs[INI]; m.fs[LOG] += line(2).encode()
    expect(start(m) == -1 and log_of(m) == HEADER + line(2), 'a removed one: no start, the log waits')
    # a poll with no room for the count
    m = machine(text); start(m); work(m)
    expect(poll(m, 0) == (OK, None), 'the poll takes a NULL count')


# ---- the account: the token and the user name in the card's scrobble.ini, the check ----

def forget(m): call(m, PSYMS['scrobup_forget'], count=10000)
def rejected(m): return call(m, PSYMS['scrobup_rejected'], count=10000)
def kind(m): return call(m, PSYMS['scrobup_kind'], count=10000)
def owner(m): return call(m, PSYMS['scrobup_owner'], count=10000)
def invalid(m): return call(m, PSYMS['scrobup_invalid'], count=10000)
def ini_of(m): return m.fs.get(INI)
def opened(m, path): return [c for c in m.log if c[0] == 'open' and c[1] == path]


def account(m, n=None):
    """scrobup_account: (result, the name's bytes)."""
    n = NAME_MAX if n is None else n
    buf = m.alloc(n + 8); m.u.mem_write(buf, b'\xaa' * (n + 8))
    r = call(m, PSYMS['scrobup_account'], a0=buf, a1=n, count=1 << 24)
    raw = bytes(m.u.mem_read(buf, n + 8))
    assert raw[n:] == b'\xaa' * 8 and b'\0' in raw[:n], raw
    return r, raw[:raw.index(b'\0')]


def check_start(m, owner=UI):
    m.thread = None
    return s32(call(m, PSYMS['scrobup_check_start'], a0=owner, count=1 << 30))


def check(m):
    """A whole check: the poll's (result, sent)."""
    r = check_start(m)
    assert r == 1 and m.thread, r
    work(m)
    return poll(m)


def answer(name='rob', valid=True, **kw):
    """validate-token's answer."""
    d = {'code': 200, 'message': 'Token valid.' if valid else 'Token invalid.', 'valid': valid}
    if name is not None: d['user_name'] = name
    return {'body': json.dumps(d).encode(), **kw}


def account_tests(ctx):
    """scrobup_account / scrobup_token_clear: the account read from the card's file (the only way to set a token: the payload has no setter), the user name, the answer kept in RAM, Sign Out's atomic write, no card, nothing on flash."""
    expect = ctx.expect
    expect((NAME_MAX, ANS, REJ_MAX, INI_MAX) == (64, 2048, 128, 4096), 'the limits: a user name of 63 bytes, an answer of 2 KB, 128 runs of refused listens, a scrobble.ini of 4 KB')
    expect('scrobup_token_set' not in PSYMS, 'the payload has no routine that sets a token: sign-in is the file on the card')   # noqa: F821
    m = machine(token=None)
    expect(account(m) == (0, b'') and not wrote(m) and 'curl_easy_init' not in names(m), 'no file: no account, nothing written, no network')
    m.log = []
    expect(account(m) == (0, b'') and not opened(m, INI), 'asked again: the answer is kept, the file is not opened')
    m = machine(); m.log = []
    expect(account(m) == (1, b'') and not wrote(m) and 'curl_easy_init' not in names(m), 'a token in the file and no USER line: an account without a user name (not checked yet); reading it writes nothing and asks no network')
    expect(not [c for c in m.log if c[0] in ('open', 'access', 'unlink', 'mkdir', 'rename') and '/mnt/data/m1plus/' in c[1]] and OLD_FLASH not in m.fs, 'nothing of the account is read from or written to the flash')
    m.log = []
    expect(account(m) == (1, b'') and not opened(m, INI), 'kept in RAM: a page refresh reads nothing')
    # the user name
    m = machine(name='rob')
    expect(account(m) == (1, b'rob'), 'USER is the user name')
    for what, val, want in (('spaces inside and around', '  Rob  Kaye ', b'Rob  Kaye'), ('quotes and a backslash', 'a"b\\c\'', b'a"b\\c\''), ('CJK', '坂本龍一', '坂本龍一'.encode()), ('= and ; inside', 'a=b;c', b'a=b;c')):
        m = machine(raw=ini() + 'USER=' + val + '\n')
        expect(account(m) == (1, want), f'a user name with {what}: {want!r} ({account(m)})')
    m = machine(raw=ini().encode() + b'USER= r\x01o\tb\x7f\xc2\x85\xff \xe9 \xc3\xa9\xe4\xb8 \n')
    expect(account(m) == (1, 'rob  é'.encode()), f'a hand-made name: control bytes, DEL, C1 controls and bytes that are not UTF-8 are dropped ({account(m)})')
    m = machine(name='名' * 40)
    expect(account(m) == (1, ('名' * 21).encode()), 'a name over 63 bytes is cut on a character boundary')
    m = machine(name='robert')
    expect(account(m, 4) == (1, b'rob') and account(m, 1) == (1, b''), 'a short buffer is never overrun')
    expect(call(m, PSYMS['scrobup_account'], a0=0, a1=0, count=1 << 20) == 1, 'and none is needed')
    # no sign-out on the device: the payload has no call that removes an account
    expect(not [n for n in ('scrobup_token_clear', 'scrobup_lastfm_clear', 'scrobup_token_set') if n in PSYMS], 'the payload has no call that sets or removes an account')
    # storage failures
    m = machine(name='rob'); m.fail.add(('open', INI))
    expect(account(m) == (0, b'') and ini_of(m) == ini(name='rob').encode(), 'a file that is there and does not open: no account now, and it is never written over')
    m = machine(name='rob'); m.fail.add(('read', INI))
    expect(account(m) == (0, b'') and ini_of(m) == ini(name='rob').encode(), 'nor one that does not read')
    m = machine(name='rob'); m.calloc_fail = True
    expect(account(m) == (0, b'') and ini_of(m) == ini(name='rob').encode(), 'no memory to read the file with: no account now, nothing written')
    m.calloc_fail = False
    expect(account(m) == (1, b'rob'), 'and it is read again by the next call')
    # no card
    m = machine(name='rob'); m.card_mounted = False; m.log = []
    expect(account(m) == (0, b'') and start(m) == -1 and check_start(m) == -1, 'no mounted card: Not Set; nothing starts')
    expect(not [c for c in m.log if c[0] in ('open', 'access', 'unlink', 'rename') and c[1].startswith('/mnt/mmc/scrobble')] and not wrote(m) and ini_of(m) == ini(name='rob').encode(), 'and nothing under the mount point is opened or written')
    expect(account(m) == (0, b''), '(still no account)')
    m.card_mounted = True
    expect(account(m) == (0, b''), '(the card is back: what was read is kept ...)')
    forget(m)
    expect(account(m) == (1, b'rob'), '... until scrobup_forget: then the file is read again')
    # edited on a computer: no reboot
    m = machine(name='rob'); account(m)
    m.fs[INI] = b'[LISTENBRAINZ]\r\nTOKEN=typed-on-a-pc\r\nUSER=someone\r\n'; forget(m)
    expect(account(m) == (1, b'someone'), 'a file changed on a computer is the account after scrobup_forget (a page that opens, an Upload Scrobbles tap, the automatic upload\'s look)')
    m.site.answers = [{}]; m.fs[LOG] = (HEADER + line(0)).encode()
    expect(upload(m) == (OK, 1) and m.site.reqs[-1]['heads'][0] == 'Authorization: Token typed-on-a-pc', 'and the upload sends with it')


def ini_tests(ctx):
    """How scrobble.ini is read: a BOM, CRLF, blanks, either case, comments, other sections and keys; the first section and the first key; a file over the cap."""
    expect = ctx.expect
    T = TOKEN
    lastfm = '[LASTFM]\nUSER=me\nPASSWORD=secret\nAPI_KEY=k\nAPI_SECRET=s\n'
    for what, raw, want in (
            ('a UTF-8 BOM', b'\xef\xbb\xbf' + ini(name='rob').encode(), (1, b'rob')),
            ('a BOM and CRLF', b'\xef\xbb\xbf' + ini(name='rob', eol='\r\n').encode(), (1, b'rob')),
            ('lower case', f'[listenbrainz]\ntoken={T}\nuser=rob\n', (1, b'rob')),
            ('mixed case', f'[ListenBrainz]\nToken={T}\nUser=rob\n', (1, b'rob')),
            ('blanks around = and the values', f'[LISTENBRAINZ]\nTOKEN =  {T} \t\nUSER\t=\trob  \n', (1, b'rob')),
            ('blanks before the lines and inside the brackets', f'  [ LISTENBRAINZ ]  \n\t TOKEN={T}\n   USER=rob\n', (1, b'rob')),
            ('blanks and CRLF', f' [listenbrainz] \r\n token = {T} \r\n user = rob \r\n', (1, b'rob')),
            ('; and # comment lines and empty lines', f'; my scrobbling\n\n# ListenBrainz\n[LISTENBRAINZ]\n; the token\n\nTOKEN={T}\n# TOKEN=not-this\n;USER=nobody\nUSER=rob\n', (1, b'rob')),
            ('text behind the bracket', f'[LISTENBRAINZ] ; mine\nTOKEN={T}\n', (1, b'')),
            ('unknown keys', f'[LISTENBRAINZ]\nURL=https://example.org\nTOKEN={T}\nTOKENS=x\nXTOKEN=y\nUSERNAME=z\nUSER=rob\n', (1, b'rob')),
            ('lines that are no key', f'[LISTENBRAINZ]\nhello there\nTOKEN={T}\n', (1, b'')),
            ('a [LASTFM] section before it', lastfm + ini(name='rob'), (1, b'rob')),
            ('a [LASTFM] section behind it', ini() + lastfm, (1, b'')),
            ('unknown sections around it', '[GENERAL]\nTOKEN=not-this\nUSER=nobody\n' + ini(name='rob') + '[OTHER]\nTOKEN=nor-this\nUSER=nobody\n', (1, b'rob')),
            ('USER before TOKEN', f'[LISTENBRAINZ]\nUSER=rob\nTOKEN={T}\n', (1, b'rob')),
            ('TOKEN twice', f'[LISTENBRAINZ]\nTOKEN={T}\nTOKEN=second\nUSER=rob\nUSER=bob\n', (1, b'rob')),
            ('the section twice', ini(name='rob') + '[LASTFM]\nUSER=me\n' + ini('second', 'bob'), (1, b'rob')),
            ('no newline at the end', f'[LISTENBRAINZ]\nTOKEN={T}', (1, b'')),
            ('an empty USER', f'[LISTENBRAINZ]\nTOKEN={T}\nUSER=\n', (1, b'')),
            ('an empty TOKEN', '[LISTENBRAINZ]\nTOKEN=\nUSER=rob\n', (0, b'')),
            ('TOKEN with blanks only', '[LISTENBRAINZ]\nTOKEN = \t \r\n', (0, b'')),
            ('a commented TOKEN', f'[LISTENBRAINZ]\n;TOKEN={T}\n', (0, b'')),
            ('TOKEN before any section', f'TOKEN={T}\n', (0, b'')),
            ('TOKEN in [LASTFM] only', f'[LASTFM]\nTOKEN={T}\n[LISTENBRAINZ]\n', (0, b'')),
            ('another section\'s name that starts alike', f'[LISTENBRAINZ2]\nTOKEN={T}\n', (0, b'')),
            ('a token with a comment behind it', f'[LISTENBRAINZ]\nTOKEN={T} ; mine\n', (0, b'')),
            ('a quoted token', f'[LISTENBRAINZ]\nTOKEN="{T} x"\n', (0, b'')),
            ('a BOM in the second line only', b'\n\xef\xbb\xbf[LISTENBRAINZ]\nTOKEN=' + T.encode() + b'\n', (0, b'')),
            ('UTF-16', ('\ufeff' + ini()).encode('utf-16-le'), (0, b'')),
            ('a picture', bytes(range(256)) * 12, (0, b''))):
        m = machine(raw=raw); m.log = []
        got = account(m)
        expect(got == want and not wrote(m), f'{what}: {"the token" if want[0] else "no token"}{", user " + want[1].decode() if want[1] else ""} ({got})')
        if want[0]:
            m.fs[LOG] = (HEADER + line(0)).encode(); m.site.answers = Lastfm()   # (a [LASTFM] section with its four keys is an account too: its service answers)
            expect(upload(m) == (OK, 1) and m.site.reqs[0]['heads'][0] == 'Authorization: Token ' + T, f'{what}: the upload sends that token')
    # a file over SU_INI_MAX: the whole lines of its first SU_INI_MAX bytes are read, and it is never rewritten
    pad = '; a long comment line to fill the file up\n'
    big = ini(name='rob') + pad * (INI_MAX // len(pad) + 1) + lastfm
    m = machine(raw=big, answers=[answer('robert')]); m.log = []
    expect(len(big) > INI_MAX and account(m) == (1, b'rob'), 'a file over 4 KB with the account at its start: read')
    expect(check(m) == (DISK, 0) and not wrote(m) and ini_of(m) == big.encode() and account(m) == (1, b'rob'), 'a check with another user name cannot write it either: a storage failure, the file as it was')
    m.fs[LOG] = (HEADER + line(0)).encode(); m.site.answers = [{}]
    expect(upload(m) == (OK, 1), 'the token still uploads')
    m = machine(raw=pad * (INI_MAX // len(pad) + 1) + ini(name='rob'))
    expect(account(m) == (0, b'') and not wrote(m), 'the account behind the first 4 KB: not read')
    head = '[LISTENBRAINZ]\n' + pad * ((INI_MAX - 15 - 20) // len(pad))
    cut = head + ';' * (INI_MAX - 20 - len(head) - 1) + '\nTOKEN=' + TOKEN + '\nUSER=rob\n'
    m = machine(HEADER + line(0), raw=cut)
    expect(len(cut) > INI_MAX and cut.index(TOKEN) < INI_MAX < cut.index(TOKEN) + len(TOKEN) and account(m) == (0, b'') and start(m) == -1, 'a TOKEN line that crosses the 4096th byte: not read (a cut token is never sent)')
    fits = ini(name='rob') + ';' * (INI_MAX - len(ini(name='rob')) - 1) + '\n'
    m = machine(raw=fits, answers=[answer('bob')])
    expect(len(fits) == INI_MAX and account(m) == (1, b'rob') and check(m) == (OK, 0) and len(ini_of(m)) == INI_MAX and account(m) == (1, b'bob'), 'a file of exactly 4096 bytes is read and rewritten')
    m = machine(raw=fits, answers=[answer('robert')])
    expect(check(m) == (DISK, 0) and ini_of(m) == fits.encode() and INI_TMP not in m.fs, 'an edit that would make the file longer than 4096 bytes (a longer user name) is refused: a storage failure, the file as it was')
    full = ini() + ';' * (INI_MAX - len(ini()) - 1) + '\n'
    m = machine(raw=full, answers=[answer()])
    expect(len(full) == INI_MAX and check(m) == (DISK, 0) and ini_of(m) == full.encode() and account(m) == (1, b''), 'nor is a USER line added to a file with no room for it')


def edit_tests(ctx):
    """The in-place rewrite, by a valid check (USER) only: the USER line in [LISTENBRAINZ] changes; comments, other sections, line order and line ends
    are kept byte for byte. The device never writes a token, a TOKEN line, the section or the file."""
    expect = ctx.expect
    T = TOKEN

    def edited(before, name):
        """The file after a check that confirmed `name`."""
        m = machine(raw=before, answers=[answer(name)])
        r = check(m)
        assert r == (OK, 0) and INI_TMP not in m.fs, r
        return m.fs[INI].decode('utf-8')
    lastfm = '[LASTFM]\nUSER = me\nPASSWORD=secret\nAPI_KEY=k\nAPI_SECRET=s\n'
    tline = f'  Token =  {T}  \n'
    full = ('; my scrobble settings\n\n' + lastfm + '\n# ListenBrainz\n[ListenBrainz]\n' + tline + '; a note\nUser\t=\told name\nEXTRA=1\n\n'
            '[OTHER]\nTOKEN=not-this\nUSER=nor-this\n[listenbrainz]\nTOKEN=second-section\n')
    got = edited(full, name='rob')
    expect(got == full.replace('User\t=\told name\n', 'User\t=\trob\n'), f'a confirmed user name in a file with comments, [LASTFM] and odd spacing: the USER value alone is replaced (key, blanks and line end stay), every other byte is as it was ({got!r})')
    expect(lastfm in got and got.count('USER = me') == 1 and 'USER=nor-this' in got and 'TOKEN=second-section' in got and tline in got, '[LASTFM], the other section, a second [listenbrainz] and the token are untouched')
    # no USER line yet (a file as the user writes it): it is added behind the TOKEN line
    fresh = full.replace('User\t=\told name\n', '')
    got = edited(fresh, name='rob')
    expect(got == fresh.replace(tline, tline + 'USER=rob\n'), f'no USER line: one is added right behind the TOKEN line, inside our section ({got!r})')
    crlf = '\ufeff[LASTFM]\r\nUSER=me\r\nPASSWORD=secret\r\n[listenbrainz]\r\ntoken = ' + T
    got = edited(crlf.encode('utf-8'), name='rob')
    expect(got == crlf + '\r\nUSER=rob\r\n', f'a BOM, CRLF and the token line without a line end at the file\'s end: USER is added with the file\'s line ends ({got!r})')
    got = edited(f'[LISTENBRAINZ]\nTOKEN={T}', name='rob')
    expect(got == ini(name='rob'), 'a TOKEN line without a line end at the file\'s end')
    got = edited(ini() + lastfm, name='rob')
    expect(got == ini(name='rob') + lastfm and got.count('USER = me') == 1, 'a [LASTFM] section behind ours: USER goes into our section; its USER is not ours')
    got = edited(lastfm + ini(), name='me')
    expect(got == lastfm + ini(name='me'), 'a [LASTFM] section before ours with a USER of its own: ours is added, that one is not taken for it')
    got = edited(f'[LISTENBRAINZ]\nUSER=old name\nTOKEN={T}\n', name='rob')
    expect(got == f'[LISTENBRAINZ]\nUSER=rob\nTOKEN={T}\n', 'USER before TOKEN: corrected where it is by a check')
    doubled = f'[LISTENBRAINZ]\nTOKEN={T}\nTOKEN=second\nUSER=a\nUSER=b\n'
    got = edited(doubled, name='rob')
    expect(got == doubled.replace('USER=a\n', 'USER=rob\n'), f'doubled lines: the first USER is ours, as it is read ({got!r})')
    # the device adds no token, no TOKEN line, no section and no file
    for what, raw in (('no file', None), ('an empty file', ''), ('[LASTFM] only', lastfm), ('the section without lines', '[LISTENBRAINZ]\n; nothing yet\n' + lastfm), ('an empty TOKEN=', '[LISTENBRAINZ]\nTOKEN=\n' + lastfm),
                      ('a value that is no token', '[LISTENBRAINZ]\nTOKEN = a b c ; no token\n')):
        m = machine(token=None, raw=raw); m.log = []
        expect(account(m) == (0, b'') and check_start(m) == -1 and not wrote(m) and ini_of(m) == (None if raw is None else raw.encode()), f'{what}: no account, no check, nothing written ({ini_of(m)!r})')
    # the token taken out of the file on a computer and written back: its check puts USER back
    m = machine(raw=full.replace('User\t=\told name\n', ''), answers=[answer('rob')])
    expect(account(m) == (1, b'') and check(m) == (OK, 0) and account(m) == (1, b'rob'), 'a token without a name: its check')
    expect(m.fs[INI].decode() == full.replace(tline, tline + 'USER=rob\n').replace('User\t=\told name\n', ''), 'USER goes behind the TOKEN line; the rest is as it was')
    m.log = []
    expect(check(m) == (OK, 0) and not wrote(m), 'checked again with the same answer: nothing is written')
    expect(not [p for p in m.fs if p in (OLD_FLASH, OLD_CARD)], 'no other account file is made')


def check_tests(ctx):
    """scrobup_check_start: validate-token on the worker thread; a valid answer writes the user name back as USER=, an invalid one keeps the token, a failure changes nothing."""
    expect = ctx.expect
    m = machine(answers=[answer()]); m.log = []
    expect(check_start(m) == 1 and m.thread and busy(m) == 1 and kind(m) == CHECK and not wrote(m) and not m.site.reqs, 'a check starts one thread; the start writes nothing and asks the network nothing')
    expect(poll(m) == (0, 0xdead), 'the poll while it runs: 0')
    work(m)
    expect(not wrote(m) and ini_of(m) == ini().encode(), 'the thread writes nothing')
    res = poll(m)
    expect(res == (OK, 0) and busy(m) == 0 and 'pthread_join' in names(m) and poll(m) == (0, 0xdead), f'the poll once it is over: valid, 0 listens, the thread joined, the result given once ({res})')
    expect(ini_of(m) == ini(name='rob').encode() and INI_TMP not in m.fs and account(m) == (1, b'rob'), f'the user name is written back as USER= behind the token ({ini_of(m)!r})')
    expect(('fsync', INI_TMP) in m.log and ('rename', INI_TMP, INI) in m.log and not [c for c in m.log if c[0] in ('open', 'access', 'unlink') and (c[1].startswith('/mnt/mmc/.') or c[1].startswith('/mnt/data/m1plus/'))],
           'atomically; the log, its archives and the flash are not touched')
    q = m.site.reqs
    expect(len(q) == 1 and q[0]['url'] == CHECK_URL and q[0]['heads'] == ['Authorization: Token ' + TOKEN] and q[0]['body'] is None and 60 not in q[0]['o'], f'one GET of validate-token with the token\'s header and no body ({q[0]["url"]}, {q[0]["heads"]})')
    o = q[0]['o']
    expect(o[10065] == '/etc/m1plus-cacert.pem' and o[64] == 1 and o[81] == 2 and o[181] == 2 and 52 not in o and o[78] == 15 and o[13] == 60 and o[99] == 1 and o[20011] and o[10001], 'the upload\'s setup: the CA bundle, peer and host verified, HTTPS only, no redirect, the same time limits; the answer is collected')
    expect(m.site.held == [0] and not [c for c in m.log if len(c) == 2 and c[1] == PSYMS['sc_mutex']], 'the log\'s lock is not taken')
    m.log = []
    expect(check(m) == (OK, 0) and not wrote(m) and account(m) == (1, b'rob'), 'checked again with the same answer: nothing is written')
    m.site.answers = [answer('robert')]
    expect(check(m) == (OK, 0) and ini_of(m) == ini(name='robert').encode() and account(m) == (1, b'robert'), 'a changed name replaces the old one: USER is a display cache any valid check corrects')
    m = machine(raw=ini() + 'USER=somebody else\n', answers=[answer()])
    expect(account(m) == (1, b'somebody else') and check(m) == (OK, 0) and ini_of(m) == ini(name='rob').encode(), 'a USER written by hand is corrected too')
    expect(upload(machine(HEADER + line(0), name='rob')) == (OK, 1), 'an account with a name uploads')
    for what, ans in (('in small pieces', answer(chunk=7)), ('with white space and other members', {'body': b' {\n "user_name" : "rob", "extra": {"valid": false, "a": [1, 2, {"user_name": "x"}]},\r\n "valid" :\ttrue , "code": 200 }\n'}),
                      ('the members twice', {'body': b'{"valid":true,"user_name":"rob","valid":false,"user_name":"eve"}'})):
        m = machine(answers=[ans])
        expect(check(m) == (OK, 0) and account(m) == (1, b'rob'), f'the answer {what}: valid, rob ({account(m)})')
    # invalid: the token is kept
    for what, ans in (('"valid": false', answer(None, False)), ('"valid": false with a name', answer('rob', False)), ('a 401', {'code': 401, 'body': b'{"code":401,"error":"Invalid authorization token."}'})):
        for nm in (None, 'rob'):
            m = machine(name=nm, answers=[ans]); m.log = []
            res = check(m)
            expect(res == (AUTH, 0) and ini_of(m) == ini(name=nm).encode() and not wrote(m) and account(m)[0] == 1, f'{what}: the token is refused, and kept; nothing is written ({res})')
    # failures: nothing changes
    big = json.dumps({'code': 200, 'message': 'x' * ANS, 'valid': True, 'user_name': 'rob'}).encode()
    for what, ans in (('no connection', {'rc': 7, 'code': 0}), ('a timeout', {'rc': 28, 'code': 0}), ('a certificate that does not verify', {'rc': 60, 'code': 0}), ('500', {'code': 500, 'body': answer()['body']}), ('429', {'code': 429}),
                      ('400', {'code': 400, 'body': b'{"code":400,"error":"You need to provide an Authorization header."}'}), ('a redirect', {'code': 302, 'body': answer()['body']}), ('an empty answer', {'body': b''}),
                      ('a page that is no JSON', {'body': b'<html><body>valid true user_name rob</body></html>'}), ('an answer cut short', {'body': answer()['body'][:-1]}), ('an array', {'body': b'[{"valid":true,"user_name":"rob"}]'}),
                      ('"valid" as a string', {'body': b'{"valid":"true","user_name":"rob"}'}), ('"valid": 1', {'body': b'{"valid":1,"user_name":"rob"}'}), ('"valid": null', {'body': b'{"valid":null,"user_name":"rob"}'}),
                      ('no "valid"', {'body': b'{"code":200,"user_name":"rob"}'}), ('valid without a name', answer(None)), ('a name that is a number', {'body': b'{"valid":true,"user_name":42}'}), ('an empty name', answer('')),
                      ('a name of control characters', answer('\x01\n\t \x7f')), ('the members one level down', {'body': b'{"payload":{"valid":true,"user_name":"rob"}}'}), ('an unclosed string', {'body': b'{"valid":true,"user_name":"rob'}),
                      ('an answer over 2 KB', {'body': big}), ('a transfer that broke after the answer', {'rc': 56, 'code': 200, 'body': answer()['body'], 'partial': True})):
        for nm in (None, 'rob'):
            m = machine(name=nm, answers=[ans]); m.log = []
            res = check(m)
            expect(res == (FAIL, 0) and ini_of(m) == ini(name=nm).encode() and not wrote(m) and account(m) == (1, (nm or '').encode()) and 'curl_easy_cleanup' in names(m), f'{what}: a failure, the account is as it was ({res})')
    expect(len(big) > ANS and len(answer('名' * 100)['body']) < ANS, '(the long answer is over the limit, the long names are under it)')
    # a hostile user name
    for what, name, want in (('quotes and a backslash', 'a"b\\c\'<&>', b'a"b\\c\'<&>'), ('control characters', 'ro\x01b\r\nX: 1\t!', b'ro b  X: 1 !'), ('DEL and C1 controls', 'r\x7fo\x85b\x9f', b'rob'), ('spaces around', '  rob kaye  ', b'rob kaye'),
                             ('over-long', 'x' * 500, b'x' * (NAME_MAX - 1)), ('over-long CJK', '名' * 100, ('名' * 21).encode()), ('an emoji', 'rob 🎧', 'rob 🎧'.encode()), ('a NUL', 'ro\x00b', b'rob'),
                             ('what looks like a section', '[LASTFM]', b'[LASTFM]'), ('what looks like a key', 'TOKEN=evil', b'TOKEN=evil'), ('a line end and a key', 'rob\nTOKEN=evil', b'rob TOKEN=evil')):
        m = machine(answers=[answer(name)])
        res = check(m); got = account(m)
        expect(res == (OK, 0) and got == (1, want), f'a name with {what}: kept as {want!r} ({res}, {got})')
        expect(ini_of(m) == ini().encode() + b'USER=' + want + b'\n' and len(want) < NAME_MAX and not [b for b in want if b < 0x20 or b == 0x7f], f'{what}: the file has the token\'s line and one USER line, without a control byte: a name cannot add a line')
        m2 = machine(HEADER + line(0), raw=ini_of(m))
        expect(upload(m2) == (OK, 1) and m2.site.reqs[0]['heads'][0] == 'Authorization: Token ' + TOKEN, f'{what}: the token still uploads, unchanged')
    m = machine(answers=[{'body': b'{"valid":true,"user_name":"r\\u0000o\\ud83c\\udfa7b\\ud800\\n\xff\xc3"}'}])
    expect(check(m) == (OK, 0) and account(m) == (1, 'ro🎧b'.encode()), f'escapes: a pair is one character, a NUL, a lone surrogate and bytes that are not UTF-8 are dropped ({account(m)})')
    # the token changes while the check runs
    def during(i): m.fs[INI] = ini('another-token').encode()
    m = machine(answers=[answer()], during=during)
    expect(check(m) == (FAIL, 0) and ini_of(m) == ini('another-token').encode() and account(m) == (1, b''), 'another token in the file meanwhile: the name is not given to it')
    m = machine(answers=[answer()])
    expect(check_start(m) == 1, '(a check runs)')
    m.fs[INI] = b'[LISTENBRAINZ]\nTOKEN=\n'; work(m)
    expect(poll(m) == (FAIL, 0) and ini_of(m) == b'[LISTENBRAINZ]\nTOKEN=\n' and account(m) == (0, b''), 'the token taken out of the file meanwhile: no account comes back')
    def during(i): m.card_mounted = False
    m = machine(answers=[answer()], during=during); m.log = []
    expect(check(m) == (FAIL, 0) and not wrote(m) and ini_of(m) == ini().encode(), 'the card gone meanwhile (a computer has it): nothing is written, no name')
    for fail in (('write', INI_TMP), ('rename', INI)):
        m = machine(answers=[answer()]); m.fail.add(fail)
        expect(check(m) == (DISK, 0) and ini_of(m) == ini().encode() and INI_TMP not in m.fs and account(m) == (1, b''), f'the name is not written ({fail[0]}): a storage failure, the token stays')
    # when no check starts
    for what, raw in (('no file', None), ('an empty file', ''), ('a token with a space inside', ini('abc def'))):
        m = machine(token=None, raw=raw); m.log = []
        expect(check_start(m) == -1 and m.thread is None and 'pthread_create' not in names(m) and busy(m) == 0, f'{what}: -1, no thread')
    m = machine(); m.card_mounted = False; m.log = []
    expect(check_start(m) == -1 and 'pthread_create' not in names(m) and not [c for c in m.log if c[0] == 'open' and c[1].startswith('/mnt/mmc')], 'no mounted card: -1 (the token is on the card), the mount point is not opened')
    for k in (KILL, '/mnt/data/m1plus-off'):
        m = machine(); m.present.add(k); m.log = []
        expect(check_start(m) == -1 and 'pthread_create' not in names(m) and 'curl_global_init' not in names(m) and not opened(m, INI), f'the kill switch ({k}): -1, nothing read')
    m = machine(); m.thread_ok = False
    expect(check_start(m) == -1 and busy(m) == 0, 'no thread: -1, not busy')


def exclusive_tests(ctx):
    """One thread: an upload and a check never run together."""
    expect = ctx.expect
    text = HEADER + line(0)
    m = machine(text, answers=[{}])
    expect(start(m) == 1 and kind(m) == UPLOAD, 'an upload runs')
    th = m.thread; m.log = []
    expect(check_start(m) == 0 and m.thread is None and 'pthread_create' not in names(m) and kind(m) == UPLOAD and busy(m) == 1, 'a check while it runs: 0, no second thread')
    m.thread = th; work(m)
    expect(check_start(m) == 0 and kind(m) == UPLOAD, 'over but not polled: still 0')
    expect(poll(m) == (OK, 1) and len(m.site.reqs) == 1 and m.site.reqs[0]['url'] == URL, 'the upload\'s result is the upload\'s')
    m.site.answers = [answer()]
    expect(check_start(m) == 1 and kind(m) == CHECK and busy(m) == 1, 'then a check starts')
    th = m.thread; m.log = []; m.fs[LOG] += line(1).encode()
    expect(start(m) == 0 and m.thread is None and 'pthread_create' not in names(m) and check_start(m) == 0 and kind(m) == CHECK, 'an upload, or a second check, while it runs: 0')
    m.thread = th; work(m)
    expect(start(m) == 0 and log_of(m) == HEADER + line(1) and len(m.site.reqs) == 2, 'over but not polled: still 0, the log waits')
    expect(poll(m) == (OK, 0) and account(m) == (1, b'rob') and kind(m) == CHECK, 'the check\'s result: no listens, the name')
    m.site.answers = [{}]
    expect(upload(m) == (OK, 1) and kind(m) == UPLOAD and rejected(m) == 0 and [r['url'] for r in m.site.reqs] == [URL, CHECK_URL, URL], 'then the upload runs')


def judge(bad=(), alone=None, batch=None):
    """A service that refuses (400) every request holding a listen of line(i), i in bad, and takes the others. alone: {i: answer} for a request of that one listen;
    batch: {i: answer} for a request of several listens holding it."""
    bad, alone, batch = {T0 + i for i in bad}, {T0 + i: a for i, a in (alone or {}).items()}, {T0 + i: a for i, a in (batch or {}).items()}

    def f(req):
        p = [x['listened_at'] for x in req['json']['payload']]
        if len(p) == 1 and p[0] in alone: return alone[p[0]]
        if len(p) > 1 and set(p) & set(batch): return batch[min(set(p) & set(batch))]
        return {'code': 400} if bad & set(p) else {}
    return f


def sizes(m): return [len(r['json']['payload']) for r in m.site.reqs]
def rej_of(m): return m.fs[REJ].decode('utf-8', 'replace') if REJ in m.fs else None


def reject_tests(ctx):
    """HTTP 400: the batch is sent again one listen a request; the listens refused alone leave the log for .scrobbler.log.rejected, the others are sent, and the upload goes on."""
    expect = ctx.expect
    lines = [line(i) for i in range(120)]
    text = HEADER + ''.join(lines)
    m = machine(text, answers=judge([70])); m.log = []
    res = upload(m)
    expect(res == (OK, 119) and rejected(m) == 1 and sizes(m) == [50, 50] + [1] * 50 + [20], f'one listen the service refuses, in the second of three batches: that batch goes again listen by listen and the upload goes on; 119 sent, 1 refused ({res}, {rejected(m)}, {len(m.site.reqs)} requests)')
    expect([r['json']['payload'][0] for r in m.site.reqs[2:52]] == [listen(i) for i in range(50, 100)], 'the 50 single requests are the batch\'s listens, in order, each as it was sent before')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines[:70] + lines[71:]) and rej_of(m) == lines[70] and TMP not in m.fs, 'the log is its header; the one refused line is in .scrobbler.log.rejected, the 119 others in .sent, in the log\'s order')
    steps = [c for c in m.log if c[0] in ('rename', 'curl_perform', 'fsync')]
    expect([c[0] for c in steps].count('rename') == 1 and steps[-1] == ('rename', TMP, LOG) and ('fsync', REJ) in steps and ('fsync', SENT) in steps and min(steps.index(('fsync', REJ)), steps.index(('fsync', SENT))) > max(i for i, c in enumerate(steps) if c[0] == 'curl_perform'),
           f'one rewrite, after the last request, and the rename only after both archives are synced ({[c[0] for c in steps].count("rename")} renames)')
    expect(m.site.held == [0] * 53, 'no request under the lock')
    m.fs[LOG] += line(200).encode(); m.site.answers = [{}]
    expect(upload(m) == (OK, 1) and rejected(m) == 0 and rej_of(m) == lines[70], 'the next upload: nothing refused, the count is 0 again')
    m.fs[LOG] += line(201).encode(); m.site.answers = [{'code': 400}]; n = len(m.site.reqs)
    expect(upload(m) == (OK, 0) and rejected(m) == 1 and rej_of(m) == lines[70] + line(201) and log_of(m) == HEADER and len(m.site.reqs) == n + 1,
           'a batch of one listen answered 400 is refused as it is (one request, not sent again), and appended to the file')
    m = machine(HEADER + ''.join(lines[:51]), answers=judge([50]))
    expect(upload(m) == (OK, 50) and rejected(m) == 1 and sizes(m) == [50, 1] and rej_of(m) == lines[50] and sent_of(m) == ''.join(lines[:50]), 'the 51st line alone in the last batch: one request for it')
    # every listen refused (the service takes nothing)
    m = machine(text, answers=[{'code': 400}]); m.log = []
    res = upload(m)
    expect(res == (OK, 0) and rejected(m) == 120 and sizes(m) == ([50] + [1] * 50) * 2 + [20] + [1] * 20, f'400 for every request: done, 0 sent, 120 refused, every batch and then every listen was tried ({res}, {rejected(m)}, {len(m.site.reqs)})')
    expect(log_of(m) == HEADER and rej_of(m) == ''.join(lines) and SENT not in m.fs and not opened(m, SENT), 'the log is empty: nothing blocks the next upload; all the lines are kept in .rejected and no .sent is made')
    m.fs[LOG] += line(300).encode(); m.site.answers = [{}]
    expect(upload(m) == (OK, 1) and sent_of(m) == line(300), 'and the next listen uploads')
    # a batch refused whole, a failure in the next
    for what, ans, want in (('500', {'code': 500}, FAIL), ('401', {'code': 401}, AUTH), ('429', {'code': 429}, FAIL), ('a timeout', {'rc': 28, 'code': 0}, FAIL)):
        m = machine(text, answers=judge(range(50), batch={50: ans}))
        res = upload(m)
        expect(res == (want, 0) and rejected(m) == 50 and len(m.site.reqs) == 52, f'50 listens refused, then {what} for the next batch: {want}, 50 refused, the upload ends ({res})')
        expect(log_of(m) == HEADER + ''.join(lines[50:]) and rej_of(m) == ''.join(lines[:50]) and SENT not in m.fs, f'400s, then {what}: the refused listens have left, the failed batch and the rest stay')
        m = machine(text, answers=[ans])
        expect(upload(m) == (want, 0) and rejected(m) == 0 and log_of(m) == text and REJ not in m.fs and SENT not in m.fs, f'{what} alone retires nothing')
    # skipped lines travel with the listen after them, the ones behind the batch's last listen with that one
    junk, junk2 = line(500, rating='S'), 'just some text\n'
    body = HEADER + junk + ''.join(lines[:25]) + '# a comment\n' + junk2 + ''.join(lines[25:60]) + junk
    m = machine(body, answers=judge([25, 59]))
    res = upload(m)
    expect(res == (OK, 58) and rejected(m) == 2 and rej_of(m) == junk2 + lines[25] + lines[59] + junk and sent_of(m) == junk + ''.join(lines[:25]) + ''.join(lines[26:59]) and log_of(m) == HEADER,
           f'lines that are not sent go where the listen after them goes, those at the end where the last listen goes (the count is the listens\'); comments go nowhere ({res}, {rejected(m)}, {rej_of(m)!r})')
    m = machine(body, answers=judge(range(50)))
    res = upload(m)
    expect(res == (OK, 10) and rejected(m) == 50 and rej_of(m) == junk + ''.join(lines[:25]) + junk2 + ''.join(lines[25:50]) and sent_of(m) == ''.join(lines[50:60]) + junk, f'a batch refused whole takes its skipped lines with it ({res})')
    m = machine(HEADER + ''.join(lines[:60]) + 'w' * (LINE + 1), answers=judge([59]))
    expect(upload(m) == (OK, 59) and rej_of(m) == lines[59] + 'w' * (LINE + 1) + '\n' and log_of(m) == HEADER, 'an endless over-long tail behind a refused listen is closed with a newline there')
    # the card does not take .rejected
    for what, fail, rej in (('is not written', ('write', REJ), ''), ('does not open', ('open', REJ), None), ('does not sync', ('fsync', REJ), lines[70])):
        m = machine(text, answers=judge([70])); m.fail.add(fail)
        res = upload(m)
        expect(res == (DISK, 119) and rejected(m) == 1 and log_of(m) == text and TMP not in m.fs, f'.rejected {what}: a storage failure, the log is as it was, no temp file ({res})')
        expect(rej_of(m) == rej, f'.rejected {what}: it {"is not made" if rej is None else "has " + str(rej.count(chr(10))) + " lines"}')
        m.fail.discard(fail); m.site.reqs.clear()
        res = upload(m)
        expect(res == (OK, 119) and rejected(m) == 1 and log_of(m) == HEADER and rej_of(m) == (rej or '') + lines[70], f'.rejected {what}: the next upload tries every batch again and retires them ({res})')
    for fail in (('write', TMP), ('rename', LOG), ('write', SENT)):
        m = machine(text, answers=judge([70])); m.fail.add(fail)
        res = upload(m)
        expect(res == (DISK, 119) and log_of(m) == text and TMP not in m.fs, f'{fail[0]} of {fail[1].rsplit(".", 1)[-1]} fails with a refused listen: the log is as it was ({res})')


def narrow_tests(ctx):
    """A refused batch narrowed to its listens: one bad, several, a failure in the middle, a listen appended meanwhile, the bound on the runs one upload remembers."""
    expect = ctx.expect
    lines = [line(i) for i in range(60)]
    fifty = HEADER + ''.join(lines[:50])
    m = machine(fifty, answers=judge([17])); m.log = []
    res = upload(m)
    expect(res == (OK, 49) and rejected(m) == 1 and sizes(m) == [50] + [1] * 50, f'one bad listen in a batch of 50: 49 sent, 1 refused, 51 requests ({res}, {rejected(m)}, {len(m.site.reqs)})')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines[:17] + lines[18:50]) and rej_of(m) == lines[17] and TMP not in m.fs and [c[0] for c in m.log].count('rename') == 1,
           f'the files, exactly: the log its header, .sent the 49 lines in order, .rejected the one; one rewrite ({rej_of(m)!r})')
    for bad in ((0,), (49,), (0, 1, 25, 49), (10, 11, 12, 30), tuple(range(0, 50, 2))):
        m = machine(fifty, answers=judge(bad))
        res = upload(m)
        expect(res == (OK, 50 - len(bad)) and rejected(m) == len(bad) and sent_of(m) == ''.join(l for i, l in enumerate(lines[:50]) if i not in bad) and rej_of(m) == ''.join(lines[i] for i in bad) and log_of(m) == HEADER,
               f'refused listens {bad[:4]}{"..." if len(bad) > 4 else ""} of 50: each line in its file, both in the log\'s order ({res}, {rejected(m)})')
    m = machine(fifty, answers=judge(range(50)))
    expect(upload(m) == (OK, 0) and rejected(m) == 50 and rej_of(m) == ''.join(lines[:50]) and SENT not in m.fs and log_of(m) == HEADER, 'all 50 refused alone: all in .rejected, no .sent')
    m = machine(fifty, answers=judge(batch={0: {'code': 400}}))
    expect(upload(m) == (OK, 50) and rejected(m) == 0 and sizes(m) == [50] + [1] * 50 and sent_of(m) == ''.join(lines[:50]) and REJ not in m.fs, 'a batch refused whose listens are all taken alone: all sent, nothing refused')
    # another answer in the middle of the narrowing ends the upload; what was answered is retired, the rest stays
    text = HEADER + ''.join(lines)
    for what, ans, want in (('500', {'code': 500}, FAIL), ('401', {'code': 401}, AUTH), ('429', {'code': 429}, FAIL), ('no connection', {'rc': 7, 'code': 0}, FAIL), ('a timeout', {'rc': 28, 'code': 0}, FAIL)):
        m = machine(text, answers=judge([10], alone={20: ans})); m.log = []
        res = upload(m)
        expect(res == (want, 19) and rejected(m) == 1 and sizes(m) == [50] + [1] * 21, f'{what} for the 21st single request: {want}, 19 sent, 1 refused, nothing more is asked ({res}, {rejected(m)}, {len(m.site.reqs)})')
        expect(log_of(m) == HEADER + ''.join(lines[20:]) and sent_of(m) == ''.join(lines[:10] + lines[11:20]) and rej_of(m) == lines[10] and TMP not in m.fs and [c[0] for c in m.log].count('rename') == 1,
               f'{what}: the 20 answered lines have left, each to its file; that listen and all after it stay, in one rewrite')
        m.site.answers = judge([10])
        res = upload(m)
        expect(res == (OK, 40) and rejected(m) == 0 and log_of(m) == HEADER and sent_of(m) == ''.join(lines[:10] + lines[11:]) and rej_of(m) == lines[10], f'{what}: the next upload sends the rest; nothing is sent or refused twice ({res})')
        m = machine(text, answers=judge([10], alone={0: ans})); m.log = []
        res = upload(m)
        expect(res == (want, 0) and rejected(m) == 0 and log_of(m) == text and SENT not in m.fs and REJ not in m.fs and not wrote(m), f'{what} for the first single request: nothing was answered, nothing is moved or written ({res})')
    # a listen appended while the batch is narrowed
    extra = line(99, title='Appended meanwhile')
    for k in (1, 7, 51):
        def during(i, k=k):
            if i == k: m.fs[LOG] += extra.encode()
        m = machine(fifty, answers=judge([5, 40]), during=during)
        res = upload(m)
        expect(res == (OK, 48) and rejected(m) == 2 and log_of(m) == HEADER + extra and extra not in sent_of(m) and extra not in rej_of(m), f'a listen appended during request {k} of a narrowed batch: it stays in the log, whole ({res}, {log_of(m)!r})')
    expect(upload(m) == (OK, 1) and log_of(m) == HEADER, 'and goes with the next upload')
    # refused and taken listens in turn: one upload remembers SU_REJ runs
    many = [line(i) for i in range(2 * REJ_MAX + 2)]
    m = machine(HEADER + ''.join(many), answers=judge(range(0, 2 * REJ_MAX + 2, 2))); m.log = []
    res = upload(m)
    expect(res == (FAIL, REJ_MAX) and rejected(m) == REJ_MAX, f'every other listen refused: listen {2 * REJ_MAX} would be run {REJ_MAX + 1}; the upload ends there as a failure ({res}, {rejected(m)})')
    expect(log_of(m) == HEADER + ''.join(many[2 * REJ_MAX:]) and rej_of(m) == ''.join(many[0:2 * REJ_MAX:2]) and sent_of(m) == ''.join(many[1:2 * REJ_MAX:2]) and [c[0] for c in m.log].count('rename') == 1,
           'what was answered is retired, each listen to its file, in one rewrite; that listen and the rest stay')
    expect(upload(m) == (OK, 1) and rejected(m) == 1 and log_of(m) == HEADER, 'and the next upload goes on from there')
    m = machine(HEADER + ''.join(many), answers=judge(list(range(0, 2 * REJ_MAX, 2)) + [2 * REJ_MAX - 1]))
    expect(upload(m) == (OK, REJ_MAX + 1) and rejected(m) == REJ_MAX + 1 and log_of(m) == HEADER, f'{REJ_MAX} runs, the last of two listens in a row: listens refused in a row are one run')


def owner_tests(ctx):
    """Who started the job (the settings pages or the automatic upload), and Invalid Token (RAM only; it follows the token in the card's file)."""
    expect = ctx.expect
    text = HEADER + line(0)
    m = machine(text)
    expect(start(m, UI) == 1 and owner(m) == UI and kind(m) == UPLOAD, 'an upload the pages start: owner UI')
    work(m); poll(m); m.fs[LOG] = text.encode()
    r = start(m, AUTO); th = m.thread
    expect(r == 1 and owner(m) == AUTO and start(m, UI) == 0 and owner(m) == AUTO, 'one the automatic upload starts: owner AUTO; a start refused meanwhile changes nothing')
    m.thread = th; work(m)
    expect(owner(m) == AUTO and busy(m) == 1 and poll(m) == (OK, 1), 'over and not polled: still its owner\'s')
    m.site.answers = [answer()]
    expect(check_start(m, UI) == 1 and owner(m) == UI and kind(m) == CHECK, 'a check: its owner too')
    # both owners read the same file, at the start
    for who in (UI, AUTO):
        m = machine(text, token='old-token'); account(m); m.fs[INI] = ini().encode(); m.log = []
        res = upload(m, who)
        expect(res == (OK, 1) and m.site.reqs[0]['heads'][0] == 'Authorization: Token ' + TOKEN and not [c for c in wrote(m) if any(isinstance(x, str) and x.startswith(INI) for x in c[1:])],
               f'a start by owner {who} after the file changed: the upload runs with the file\'s token, and the file is not written ({res})')
        m = machine(text, token=None)
        expect(start(m, who) == -1, f'owner {who}, no account: no start')
    # Invalid Token
    m = machine(text, name='rob', answers=[{'code': 401}])
    expect(invalid(m) == 0, 'at rest: not invalid')
    expect(upload(m, AUTO) == (AUTH, 0) and invalid(m) == 1 and ini_of(m) == ini(name='rob').encode(), 'an upload answered 401, whoever started it: Invalid Token, the token and its name kept')
    m.log = []
    expect(invalid(m) == 1 and account(m) == (1, b'rob') and not wrote(m), 'it is RAM state: nothing is written for it')
    forget(m)
    expect(account(m) == (1, b'rob') and invalid(m) == 1, 'the file read again with the same token in it (a page that opens): still Invalid Token')
    m.card_mounted = False; forget(m)
    expect(account(m) == (0, b'') and invalid(m) == 0, '(the card away: no account)')
    m.card_mounted = True; forget(m)
    expect(account(m) == (1, b'rob') and invalid(m) == 1, 'the card back with the refused token: Invalid Token again')
    m.fs[INI] = ini('fixed-on-a-computer').encode(); forget(m)
    expect(account(m) == (1, b'') and invalid(m) == 0, 'another token written into the file on a computer: not invalid, without a reboot')
    m.fs[INI] = ini(name='rob').encode(); forget(m)
    expect(account(m) == (1, b'rob') and invalid(m) == 1, '(the refused one put back: invalid)')
    m.site.answers = [answer()]
    expect(check(m) == (OK, 0) and invalid(m) == 0, 'a valid check of it (a start by another caller: no page asks a refused token again): not invalid any more')
    forget(m)
    expect(account(m) == (1, b'rob') and invalid(m) == 0, 'and it stays so when the file is read again')
    m.site.answers = [answer(valid=False)]
    expect(check(m) == (AUTH, 0) and invalid(m) == 1, 'a check that says "valid": false: Invalid Token')
    m.site.answers = [answer()]
    expect(check(m) == (OK, 0) and invalid(m) == 0, 'a valid check clears it')
    m.site.answers = [{'code': 401}]; upload(m)
    m.site.answers = [{'code': 500}]
    expect(invalid(m) == 1 and upload(m) == (FAIL, 0) and invalid(m) == 1, 'a failure that is no answer about the token leaves it')
    m.site.answers = [{}]
    expect(upload(m) == (OK, 1) and invalid(m) == 0, 'an upload that had listens taken clears it')
    m.site.answers = [{'code': 401}]; m.fs[LOG] = text.encode(); upload(m)
    m.fs[INI] = ini('another-token').encode(); forget(m)
    expect(account(m) == (1, b'') and invalid(m) == 0, 'another token in the file clears it')
    m.site.answers = [{'code': 401}]; m.fs[LOG] = text.encode(); upload(m)
    expect(invalid(m) == 1, '(refused again)')
    # the token changed while the refused job ran: the new token is not the one that was refused
    def during(i): m.fs[INI] = ini('another-token').encode()
    m = machine(text, answers=[{'code': 401}], during=during)
    expect(upload(m) == (AUTH, 0) and invalid(m) == 0, 'a 401 for a token that was replaced meanwhile does not mark the new one')
    m = machine(text, answers=[{'code': 401}]); start(m); del m.fs[INI]; work(m)
    expect(poll(m) == (AUTH, 0) and invalid(m) == 0 and account(m) == (0, b''), 'nor an account whose file went meanwhile')


def kill_tests(ctx):
    """The kill switch during an upload: looked at between batches; the upload ends as a failure and what was sent is retired."""
    expect = ctx.expect
    lines = [line(i) for i in range(120)]
    text = HEADER + ''.join(lines)
    for k in (KILL, '/mnt/data/m1plus-off'):
        def during(i, k=k):
            if i == 1: m.present.add(k)
        m = machine(text, during=during)
        res = upload(m)
        expect(res == (FAIL, 50) and len(m.site.reqs) == 1, f'{k} appears during the first request: a failure with the 50 sent, no second request ({res}, {len(m.site.reqs)})')
        expect(log_of(m) == HEADER + ''.join(lines[50:]) and sent_of(m) == ''.join(lines[:50]) and TMP not in m.fs, f'{k}: the 50 sent are archived, the others stay')
        expect(start(m) == -1 and check_start(m) == -1, f'{k}: nothing starts while it is there')
        m.present.discard(k)
        expect(upload(m) == (OK, 70) and log_of(m) == HEADER, f'{k} removed: the next upload sends the rest')
    def during(i):
        if i == 52: m.present.add(KILL)
    m = machine(text, answers=judge(range(50)), during=during)
    res = upload(m)
    expect(res == (FAIL, 50) and rejected(m) == 50 and len(m.site.reqs) == 52 and log_of(m) == HEADER + ''.join(lines[100:]) and m.fs[REJ].decode() == ''.join(lines[:50]) and sent_of(m) == ''.join(lines[50:100]),
           f'after a refused batch (its 50 listens refused one by one) and a sent one: both are retired, the third is not sent ({res})')
    def during(i):
        if i == 5: m.present.add(KILL)
    m = machine(text, answers=judge([10]), during=during)
    res = upload(m)
    expect(res == (FAIL, 4) and rejected(m) == 0 and len(m.site.reqs) == 5 and log_of(m) == HEADER + ''.join(lines[4:]) and sent_of(m) == ''.join(lines[:4]) and REJ not in m.fs,
           f'while a refused batch is sent again listen by listen: the switch is seen before the next request; the four taken are retired ({res}, {len(m.site.reqs)})')
    def during(i): m.present.add(KILL)
    m = machine(HEADER + ''.join(lines[:10]), during=during)
    expect(upload(m) == (OK, 10) and log_of(m) == HEADER, 'during the only request: there is no batch after it, the upload is done')
    m = machine(text); m.log = []
    upload(m)
    off = [c for c in m.log if c[0] == 'access' and c[1] in (KILL, '/mnt/data/m1plus-off')]
    expect(len(m.site.reqs) == 3 and 1 <= len(off) <= 12, f'the switch is looked at at the start and before the second and third batch, not once a line ({len(off)} looks)')


def files_tests(ctx):
    """Settings Files (patch/setfiles.c) has no row for the account: nothing of it is on flash, and Reset All Settings leaves the card's scrobble.ini alone."""
    expect, P = ctx.expect, pod_pages
    S = P.SETTING_FILES
    expect('scrobble-listenbrainz' not in S and not [f for f in S + P.GUARD_FILES if 'listenbrainz' in f or 'scrobble.ini' in f] and S.index('scrobble-auto') == S.index('scrobbling') + 1,
           'no account row: scrobble-auto follows scrobbling')
    expect(not [f for f in P.RETIRED_FILES if 'listenbrainz' in f], 'and no retired file: the flash file was never in a release')
    src = ''.join(open(os.path.join(ROOT, 'patch', f)).read() for f in ('home.h', 'setfiles.c', 'scrobup.c', 'scrobup.h', 'scrobpage.c', 'scrobble.c'))
    expect('scrobble-listenbrainz' not in src and 'listenbrainz-token' not in src and 'SCROBBLE_LB' not in src and 'scrobup_import' not in src, 'the payload names neither the flash file nor the token file to import')
    m = machine(name='rob'); account(m); m.log = []
    call(m, PSYMS['setfiles_open'], count=1 << 26)
    call(m, PSYMS['setfiles_reset_all'], count=1 << 26)
    expect(ini_of(m) == ini(name='rob').encode() and not [c for c in m.log if c[0] in ('open', 'unlink', 'rename', 'access') and c[1].startswith(INI)], 'Settings Files and Reset All Settings never look at the card\'s scrobble.ini')
    expect(account(m) == (1, b'rob'), 'the account is as it was')


# ---- Last.fm beside ListenBrainz: the [LASTFM] section, the signed form, the session, the errors, the listens it ignores, two services and one log ----

LF_URL = 'https://ws.audioscrobbler.com/2.0/'
LF_USER, LF_PASS, LF_KEY, LF_SECRET = 'rob', 'pa ss&w=rd+é', '0123456789abcdef0123456789abcdef', 'fedcba9876543210fedcba9876543210'
PASS_MAX, KEY_MAX = O['SU_LF_PASS'], O['SU_LF_KEY']
LB, LF = 1, 2                                   # patch/scrobup.h SCROBUP_LB, SCROBUP_LF
LFCHECK = 2                                     # scrobup_kind: SCROBUP_LFCHECK
LF_NONE, LF_NEW, LF_IN, LF_BAD = 0, 1, 2, 3     # scrobup_lastfm


def lf_ini(user=LF_USER, pw=LF_PASS, key=LF_KEY, secret=LF_SECRET, eol='\n'):
    """The [LASTFM] section as a user writes it."""
    return f'[LASTFM]{eol}USER={user}{eol}PASSWORD={pw}{eol}API_KEY={key}{eol}API_SECRET={secret}{eol}'


def lf_sig(form, secret=LF_SECRET):
    """api_sig as Last.fm's documentation has it, from the decoded form: every parameter but format (and the signature), in the order of the names, name then value, then the secret; MD5 as hex."""
    return hashlib.md5(b''.join(k.encode() + v.encode() for k, v in sorted(form, key=lambda kv: kv[0].encode()) if k not in ('format', 'api_sig')) + secret.encode()).hexdigest()


def lf_error(n, code=403):
    """An error as the service gives it (seen with a made-up key: HTTP 403, {"message": .., "error": 10})."""
    return {'code': code, 'body': json.dumps({'message': 'Some words - and more', 'error': n}).encode()}


def lf_batch(req):
    """The listens of a track.scrobble request, in the order of their indexes."""
    f = dict(req['form']); n = len([k for k in f if k.startswith('timestamp[')])
    return [{k: f.get(f'{k}[{i}]') for k in ('artist', 'track', 'album', 'timestamp', 'duration', 'trackNumber')} for i in range(n)]


class Lastfm:
    """The scripted services. ListenBrainz: lb (an answer, or what lb(request) returns; none: 200). Last.fm: getMobileSession gives a new session key each time (auth: an error number
    instead), track.scrobble takes a batch signed with the last key given (error 9 for another one) and answers for each listen, ignored: {i: code} for line(i). script: answers
    for the Last.fm requests in order, before any of that (None: go on as above). sigs: whether each Last.fm request was signed as the documentation says."""
    def __init__(self, lb=None, ignored=None, script=None, auth=None):
        self.lb, self.ignored, self.script, self.auth, self.n, self.sk, self.sigs = lb, ignored or {}, list(script or []), auth, 0, None, []

    def __call__(self, req):
        if req['url'] != LF_URL: return self.lb(req) if callable(self.lb) else (self.lb or {})
        f = dict(req['form'])
        self.sigs.append(len(f) == len(req['form']) and f.get('api_sig') == lf_sig(req['form'], LF_SECRET) and f.get('format') == 'json')
        if self.script:
            a = self.script.pop(0)
            if a is not None: return a
        if f['method'] == 'auth.getMobileSession':
            if self.auth: return lf_error(self.auth)
            self.n += 1; self.sk = f'{self.n:032x}'
            return {'body': json.dumps({'session': {'subscriber': 0, 'name': f['username'], 'key': self.sk}}).encode()}
        if f.get('sk') != self.sk: return lf_error(9)
        out = [{'artist': {'corrected': '0', '#text': x['artist']}, 'ignoredMessage': {'code': str(self.ignored.get(int(x['timestamp']) - T0, 0)), '#text': ''}, 'albumArtist': {'corrected': '0', '#text': ''},
                'timestamp': x['timestamp'], 'album': {'corrected': '0', '#text': x['album'] or ''}, 'track': {'corrected': '0', '#text': x['track']}} for x in lf_batch(req)]
        bad = len([x for x in out if x['ignoredMessage']['code'] != '0'])
        return {'body': json.dumps({'scrobbles': {'scrobble': out if len(out) != 1 else out[0], '@attr': {'accepted': len(out) - bad, 'ignored': bad}}}).encode()}


def lf_machine(log=None, lb=False, svc=None, raw=None):
    """A machine with a Last.fm account in the card's file (and a ListenBrainz one before it when lb), the services svc."""
    m = machine(log, token=None, raw=(ini(name='rob') if lb else '') + lf_ini() if raw is None else raw)
    m.lf = m.site.answers = svc or Lastfm()
    return m


def lf_reqs(m): return [r for r in m.site.reqs if r['url'] == LF_URL]
def lb_reqs(m): return [r for r in m.site.reqs if r['url'] != LF_URL]
def methods(m): return [dict(r['form'])['method'].split('.')[1] for r in lf_reqs(m)]
def lf_stamps(m): return [[int(x['timestamp']) - T0 for x in lf_batch(r)] for r in lf_reqs(m) if dict(r['form'])['method'] == 'track.scrobble']
def lb_stamps(m): return [[x['listened_at'] - T0 for x in r['json']['payload']] for r in lb_reqs(m) if r['json']]
def configured(m): return call(m, PSYMS['scrobup_configured'], count=1 << 24)
def usable(m): return call(m, PSYMS['scrobup_usable'], count=1 << 24)
def auth(m): return call(m, PSYMS['scrobup_auth'], count=10000)


def lastfm(m, n=None):
    """scrobup_lastfm: (state, the name's bytes)."""
    n = NAME_MAX if n is None else n
    buf = m.alloc(n + 8); m.u.mem_write(buf, b'\xaa' * (n + 8))
    r = call(m, PSYMS['scrobup_lastfm'], a0=buf, a1=n, count=1 << 24)
    raw = bytes(m.u.mem_read(buf, n + 8))
    assert raw[n:] == b'\xaa' * 8 and b'\0' in raw[:n], raw
    return r, raw[:raw.index(b'\0')]


def lf_check(m, owner=UI):
    """A whole Last.fm check: the poll's (result, sent)."""
    m.thread = None
    r = s32(call(m, PSYMS['scrobup_lastfm_check_start'], a0=owner, count=1 << 30))
    assert r == 1 and m.thread, r
    work(m)
    return poll(m)


def lastfm_ini_tests(ctx):
    """The [LASTFM] section: all four keys, each usable, or the account is not set; read with the ListenBrainz section in one read; the sign-out's in-place write."""
    expect = ctx.expect
    expect((PASS_MAX, KEY_MAX) == (128, 64), 'the limits: a password up to 128 bytes, an API key, a secret and a session key up to 64')
    full = lf_ini()
    for what, raw in (('the section as written', full), ('CRLF lines', lf_ini(eol='\r\n')), ('a BOM, lower case, blanks', '﻿[ lastfm ]\n user = rob \npassword = ' + LF_PASS + ' \napi_key=' + LF_KEY + '\n  api_secret =' + LF_SECRET),
                      ('behind the ListenBrainz section', ini(name='bob') + full), ('before it', full + ini(name='bob')), ('comments and other keys between', '[LASTFM]\n; note\nUSER=rob\nSESSION=abc\n# x\nPASSWORD=' + LF_PASS + '\nAPI_KEY=' + LF_KEY + '\nAPI_SECRET=' + LF_SECRET + '\n'),
                      ('a second section of the name, which is not read', full + '[LASTFM]\nUSER=other\nPASSWORD=\n'), ('a password of 128 bytes', lf_ini(pw='p' * PASS_MAX)), ('keys of 64 bytes', lf_ini(key='k' * KEY_MAX, secret='s' * KEY_MAX))):
        m = lf_machine(raw=raw.encode())
        res = lastfm(m)
        expect(res == (LF_NEW, b'rob') and configured(m) == 1 and usable(m) == 1, f'{what}: set, not asked yet, the user name ({res})')
    for what, raw in (('no file', None), ('no section', ini()), ('no USER', full.replace('USER=rob\n', '')), ('no PASSWORD', full.replace('PASSWORD=' + LF_PASS + '\n', '')), ('no API_KEY', full.replace('API_KEY=' + LF_KEY + '\n', '')),
                      ('no API_SECRET', full.replace('API_SECRET=' + LF_SECRET + '\n', '')), ('an empty PASSWORD', lf_ini(pw='')), ('an empty USER', lf_ini(user='')), ('an empty API_KEY', lf_ini(key='')), ('an empty API_SECRET', lf_ini(secret='')),
                      ('a password of 129 bytes', lf_ini(pw='p' * (PASS_MAX + 1))), ('a control byte in the password', lf_ini(pw='ab\x01cd')), ('a key of 65 bytes', lf_ini(key='k' * (KEY_MAX + 1))), ('a secret with a space inside', lf_ini(secret='ab cd')),
                      ('a key past ASCII', lf_ini(key='abcé')), ('the keys outside the section', full.replace('[LASTFM]\n', '') + '[LASTFM]\n'), ('the keys in the ListenBrainz section', full.replace('[LASTFM]', '[LISTENBRAINZ]')),
                      ('USER only in the ListenBrainz section', ini(name='rob') + full.replace('USER=rob\n', ''))):
        m = lf_machine(raw=raw.encode() if raw is not None else b'')
        if raw is None: del m.fs[INI]
        res = lastfm(m)
        expect(res == (LF_NONE, b'') and not m.site.reqs, f'{what}: not set ({res})')
    m = lf_machine(HEADER + line(0)); m.log = []
    expect(configured(m) == 1 and usable(m) == 1 and account(m) == (0, b'') and invalid(m) == 0, 'Last.fm alone: a service is set up and usable, and ListenBrainz has no token')
    m = lf_machine(lb=True); m.log = []
    expect(account(m) == (1, b'rob') and lastfm(m) == (LF_NEW, b'rob') and configured(m) == 1 and len(opened(m, INI)) == 1, f'both sections: one read of the file answers for both ({len(opened(m, INI))})')
    forget(m); m.log = []
    expect(lastfm(m) == (LF_NEW, b'rob') and len(opened(m, INI)) == 1, 'scrobup_forget: the file is read again')
    m = machine(token=None); m.log = []
    expect(configured(m) == 0 and usable(m) == 0 and lastfm(m, 4) == (LF_NONE, b''), 'no file: nothing is set up')
    m = lf_machine(lb=True); m.card_mounted = False; m.log = []
    expect(lastfm(m) == (LF_NONE, b'') and configured(m) == 0 and not [c for c in m.log if c[0] == 'open'], 'no mounted card: not set, the mount point is not opened')
    m = lf_machine(raw=lf_ini(user='x' * 100).encode())
    expect(lastfm(m) == (LF_NEW, b'x' * (NAME_MAX - 1)) and lastfm(m, 8) == (LF_NEW, b'x' * 7), 'a long user name is cut to what a name holds, and to the caller\'s room')
    # the device never writes the section
    m = lf_machine(lb=True, svc=Lastfm(lb=answer('rob'))); m.log = []
    expect(lf_check(m) == (OK, 0) and check(m) == (OK, 0) and not wrote(m) and ini_of(m) == (ini(name='rob') + full).encode(), 'a Last.fm check and a ListenBrainz check that changes nothing: the file is not written')


def lastfm_sign_tests(ctx):
    """The requests: a form POSTed to ws.audioscrobbler.com, its parameters, their escaping, and api_sig against values worked out here."""
    expect = ctx.expect
    raw = (HEADER + line(0) + line(1, artist='AC/DC & "Live" = +1', title='a+b=c&d %41') + line(2, artist='坂本龍一', album='千のナイフ', title='東風') + line(3, album='', track='0', ln='0')).encode() \
        + b'Caf\xe9\tAlbum\t\xff title\t1\t200\tL\t1800000004\t\n' + ''.join(line(i) for i in range(5, 12)).encode()
    m = lf_machine(raw)
    res = upload(m)
    q = lf_reqs(m)
    expect(res == (OK, 12) and methods(m) == ['getMobileSession', 'scrobble'] and len(m.site.reqs) == 2, f'Last.fm alone, 12 listens: a session, then one track.scrobble ({res}, {methods(m)})')
    expect(all(r['url'] == LF_URL and r['heads'] == ['Content-Type: application/x-www-form-urlencoded'] and r['body'].endswith(b'&format=json') for r in q), f'each a form POSTed to the API root, no Authorization line, format=json ({q[0]["heads"]})')
    o = q[0]['o']
    expect(o[10065] == '/etc/m1plus-cacert.pem' and o[64] == 1 and o[81] == 2 and o[181] == 2 and 52 not in o and o[78] == 15 and o[13] == 60 and o[99] == 1, 'TLS and the bounds as for ListenBrainz: the CA bundle, peer and host verified, HTTPS only, no redirect, 15 s / 60 s')
    f = dict(q[0]['form'])
    expect(f == {'api_key': LF_KEY, 'method': 'auth.getMobileSession', 'password': LF_PASS, 'username': LF_USER, 'api_sig': f['api_sig'], 'format': 'json'} and len(q[0]['form']) == 6, f'getMobileSession: the user name, the password, the API key, the signature ({sorted(f)})')
    want = hashlib.md5(('api_key' + LF_KEY + 'methodauth.getMobileSession' + 'password' + LF_PASS + 'username' + LF_USER + LF_SECRET).encode()).hexdigest()
    expect(f['api_sig'] == want == lf_sig(q[0]['form']), f'its api_sig is MD5(api_key.. method.. password.. username.. secret), lower-case hex ({f["api_sig"]}, {want})')
    expect(b'password=pa%20ss%26w%3Drd%2B%C3%A9&' in q[0]['body'] and LF_SECRET.encode() not in q[0]['body'], f'the password percent-encoded (a space, &, =, +, UTF-8); the secret is never sent ({q[0]["body"]!r})')
    f = dict(q[1]['form']); b = lf_batch(q[1]); sk = m.lf.sk
    expect(f['method'] == 'track.scrobble' and f['sk'] == sk and f['api_key'] == LF_KEY and len(b) == 12 and len(f) == len(q[1]['form']), f'track.scrobble: the session key, the API key, 12 listens, no name twice ({len(b)})')
    expect(b[0] == {'artist': 'Miles Davis', 'track': 'Track 0', 'album': 'Kind of Blue', 'timestamp': str(T0), 'duration': '300', 'trackNumber': '2'}, f'a listen: artist[i], track[i], album[i], timestamp[i], duration[i], trackNumber[i] ({b[0]})')
    expect(b[1]['artist'] == 'AC/DC & "Live" = +1' and b[1]['track'] == 'a+b=c&d %41' and b'artist%5B1%5D=AC%2FDC%20%26%20%22Live%22%20%3D%20%2B1&' in q[1]['body'] and b'a%2Bb%3Dc%26d%20%2541' in q[1]['body'],
           f'&, =, +, %, a quote and a space arrive as they are: all percent-encoded, the brackets of the names too ({b[1]})')
    expect(b[2] == {'artist': '坂本龍一', 'track': '東風', 'album': '千のナイフ', 'timestamp': str(T0 + 2), 'duration': '300', 'trackNumber': '2'}, f'CJK as its UTF-8 bytes ({b[2]})')
    expect(b[3] == {'artist': 'Miles Davis', 'track': 'Track 3', 'album': None, 'timestamp': str(T0 + 3), 'duration': None, 'trackNumber': None}, f'no album, a length and a track number of 0: those parameters are left out ({b[3]})')
    expect(b[4]['artist'] == 'Caf�' and b[4]['track'] == '� title' and b'Caf%EF%BF%BD' in q[1]['body'], f'a byte that is not UTF-8 goes as U+FFFD ({b[4]})')
    expect([int(x['timestamp']) - T0 for x in b] == list(range(12)), 'the indexes follow the log\'s order')
    order = [k for k, _ in sorted(q[1]['form'], key=lambda kv: kv[0].encode()) if k not in ('format', 'api_sig')]
    expect(order.index('artist[10]') < order.index('artist[1]') < order.index('artist[2]') and order.index('trackNumber[0]') < order.index('track[0]') and order.index('album[9]') < order.index('api_key') < order.index('artist[0]'),
           'the order of the names is by bytes: artist[10] before artist[1], trackNumber[..] before track[..], album[..] before api_key')
    expect(f['api_sig'] == lf_sig(q[1]['form']) and m.lf.sigs == [True, True], f'api_sig over the 12 listens matches the one worked out here from the decoded form ({f["api_sig"]}, {lf_sig(q[1]["form"])})')
    # one listen, the string written out
    m = lf_machine(HEADER + line(0))
    res = upload(m); f = dict(lf_reqs(m)[1]['form'])
    want = hashlib.md5(('album[0]Kind of Blue' + 'api_key' + LF_KEY + 'artist[0]Miles Davis' + 'duration[0]300' + 'methodtrack.scrobble' + 'sk' + m.lf.sk + f'timestamp[0]{T0}' + 'trackNumber[0]2' + 'track[0]Track 0' + LF_SECRET).encode()).hexdigest()
    expect(res == (OK, 1) and f['api_sig'] == want, f'one listen: MD5(album[0].. api_key.. artist[0].. duration[0].. method.. sk.. timestamp[0].. trackNumber[0].. track[0].. secret) ({f["api_sig"]}, {want})')
    # 50 listens: every index, and the signature still matches
    m = lf_machine(HEADER + ''.join(line(i, title=f'T{i} é') for i in range(BATCH + 1)))
    res = upload(m)
    expect(res == (OK, BATCH + 1) and lf_stamps(m) == [list(range(BATCH)), [BATCH]] and m.lf.sigs == [True] * 3, f'51 listens: 50 in a request (Last.fm\'s limit), then 1; each signature matches ({res}, {m.lf.sigs})')
    # the body's bound: bytes that are not UTF-8 are 9 bytes each in the form
    fat = [line(i, title='T').encode().replace(b'\tT\t', b'\t' + b'\xff' * 2000 + b'\t') for i in range(20)]
    m = lf_machine(HEADER.encode() + b''.join(fat))
    res = upload(m)
    per = RAW // len(fat[0]); q = lf_reqs(m)[1:]
    expect(res == (OK, 20) and [len(x) for x in lf_stamps(m)] == [per, per, 20 - 2 * per] and max(len(r['body']) for r in q) < BODY and lf_batch(q[0])[0]['track'] == '�' * 2000 and m.lf.sigs == [True] * 4,
           f'a batch holds at most 16 KB of the log, so its form fits the body at 9 bytes a byte ({res}, {[len(r["body"]) for r in q]})')
    expect(RAW * 9 + BATCH * 400 < BODY, 'and that bound holds for any log')


def lastfm_session_tests(ctx):
    """The session key: asked for when a job needs one, kept in RAM with the credentials it was made from, never written; made again after an error 9, once."""
    expect = ctx.expect
    lines = [line(i) for i in range(61)]
    m = lf_machine(HEADER + ''.join(lines)); m.log = []
    expect(lastfm(m) == (LF_NEW, b'rob'), 'before the first job: set, not asked yet')
    res = upload(m)
    expect(res == (OK, 61) and methods(m) == ['getMobileSession', 'scrobble', 'scrobble'] and lf_stamps(m) == [list(range(50)), list(range(50, 61))], f'an upload: one session, then the batches ({res}, {methods(m)})')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines) and REJ not in m.fs and rejected(m) == 0 and auth(m) == 0, 'the log is its header, the 61 lines are in .sent')
    sk = m.lf.sk
    expect(lastfm(m) == (LF_IN, b'rob') and ini_of(m) == lf_ini().encode() and not [c for c in m.log if c[0] in ('write', 'rename') and c[1].startswith(INI)] and not [p for p, d in m.fs.items() if sk.encode() in d],
           'afterwards: signed in; the card\'s file is as it was, and the session key is in no file')
    expect(m.site.held == [0] * 3, 'no request under the log\'s lock')
    m.fs[LOG] += line(70).encode()
    expect(upload(m) == (OK, 1) and methods(m)[3:] == ['scrobble'] and dict(lf_reqs(m)[-1]['form'])['sk'] == sk, f'the next upload uses the session it has: no second getMobileSession ({methods(m)[3:]})')
    # the service no longer takes the key
    m.lf.sk = 'gone'; m.fs[LOG] += line(71).encode(); n = len(lf_reqs(m))
    res = upload(m)
    expect(res == (OK, 1) and methods(m)[n:] == ['scrobble', 'getMobileSession', 'scrobble'] and dict(lf_reqs(m)[-1]['form'])['sk'] == m.lf.sk != sk and log_of(m) == HEADER, f'error 9 (invalid session): the key is dropped, a new one asked for, the batch sent again ({res}, {methods(m)[n:]})')
    expect(lastfm(m) == (LF_IN, b'rob'), 'and the new one is kept')
    m.lf.script = [lf_error(9), None, lf_error(9)]; m.fs[LOG] += line(72).encode(); n = len(lf_reqs(m))
    res = upload(m)
    expect(res == (FAIL, 0) and methods(m)[n:] == ['scrobble', 'getMobileSession', 'scrobble'] and log_of(m) == HEADER + line(72) and lastfm(m) == (LF_NEW, b'rob') and auth(m) == 0,
           f'error 9 again with the new key: a failure, the log as it was, no third session in that upload; no key is kept ({res}, {methods(m)[n:]})')
    n = len(lf_reqs(m))
    expect(upload(m) == (OK, 1) and methods(m)[n:] == ['getMobileSession', 'scrobble'], 'the upload after it starts with a session')
    # other credentials in the file: the session was not made from them
    m.fs[INI] = lf_ini(pw='another').encode(); m.fs[LOG] += line(73).encode(); n = len(lf_reqs(m))
    forget(m)
    expect(lastfm(m) == (LF_NEW, b'rob'), 'another password in the file: not asked yet (the session is dropped when the file is read)')
    expect(upload(m) == (OK, 1) and methods(m)[n:] == ['getMobileSession', 'scrobble'] and dict(lf_reqs(m)[n]['form'])['password'] == 'another' and lastfm(m) == (LF_IN, b'rob'), 'the next upload asks for a session with the new password')
    # the card away and back
    m = lf_machine(HEADER + line(0)); upload(m)
    m.card_mounted = False; forget(m)
    expect(lastfm(m) == (LF_NONE, b''), 'the card gone: not set')
    m.card_mounted = True; forget(m)
    expect(lastfm(m) == (LF_NEW, b'rob'), 'and back: set, the session is asked for again')
    # a session answer that is none
    for what, ans in (('no session object', {'body': b'{"ok":1}'}), ('no key', {'body': b'{"session":{"name":"rob"}}'}), ('a key that is no key', {'body': json.dumps({'session': {'key': 'ab cd'}}).encode()}),
                      ('a key of 65 bytes', {'body': json.dumps({'session': {'key': 'k' * (KEY_MAX + 1)}}).encode()}), ('an answer cut short', {'body': b'{"session":{"key":"abc"'}), ('an empty 200', {}), ('an answer that does not fit its buffer', {'body': b'{"session":{"key":"abc"},"x":"' + b'y' * BODY + b'"}'})):
        m = lf_machine(HEADER + line(0), svc=Lastfm(script=[ans]))
        res = upload(m)
        expect(res == (FAIL, 0) and methods(m) == ['getMobileSession'] and log_of(m) == HEADER + line(0) and lastfm(m) == (LF_NEW, b'rob'), f'{what}: a failure, nothing sent ({res}, {methods(m)})')
    # the check
    m = lf_machine(HEADER + line(0)); m.log = []
    res = lf_check(m)
    expect(res == (OK, 0) and kind(m) == LFCHECK and methods(m) == ['getMobileSession'] and lastfm(m) == (LF_IN, b'rob') and log_of(m) == HEADER + line(0) and not wrote(m), f'scrobup_lastfm_check_start: a session is asked for, signed in; the log and the file untouched ({res})')
    expect(upload(m) == (OK, 1) and methods(m) == ['getMobileSession', 'scrobble'], 'the upload after a check uses the check\'s session')
    expect(lf_check(m) == (OK, 0) and methods(m)[2:] == ['getMobileSession'], 'a check always asks the service, with a session kept too')
    def during(i): m.fs[INI] = lf_ini(pw='changed meanwhile').encode()
    m = lf_machine(); m.site.during = during
    expect(lf_check(m) == (FAIL, 0) and lastfm(m) == (LF_NEW, b'rob'), 'the credentials changed while the check ran: a failure, the session is not kept for the new ones')
    m = machine(HEADER + line(0)); m.thread = None
    expect(s32(call(m, PSYMS['scrobup_lastfm_check_start'], a0=UI, count=1 << 30)) == -1 and m.thread is None, 'a Last.fm check without a Last.fm account: -1')
    m = lf_machine(); m.thread = None
    expect(check_start(m) == -1 and m.thread is None, 'a ListenBrainz check without a token: -1, with Last.fm set up too')
    m = lf_machine(lb=True); start(m); m.thread = None
    expect(s32(call(m, PSYMS['scrobup_lastfm_check_start'], a0=UI, count=1 << 30)) == 0 and m.thread is None, 'one job at a time: no Last.fm check while an upload runs')


def lastfm_error_tests(ctx):
    """Last.fm's errors: the account refused (4, 10, 26, 13), a failure to try again later (everything else), in either call."""
    expect = ctx.expect
    text = HEADER + ''.join(line(i) for i in range(3))
    for err, want in ((4, AUTH), (10, AUTH), (26, AUTH), (13, AUTH), (8, FAIL), (11, FAIL), (16, FAIL), (29, FAIL), (6, FAIL), (3, FAIL), (9, FAIL)):
        m = lf_machine(text, svc=Lastfm(auth=err)); m.log = []
        res = upload(m)
        expect(res == (want, 0) and methods(m) == ['getMobileSession'] and log_of(m) == text and SENT not in m.fs and not wrote(m), f'getMobileSession answered error {err}: {want}, nothing sent, the log untouched ({res}, {methods(m)})')
        expect((lastfm(m)[0], auth(m), usable(m)) == ((LF_BAD, LF, 0) if want == AUTH else (LF_NEW, 0, 1)), f'error {err}: {"the account is refused" if want == AUTH else "the account stands"} ({lastfm(m)[0]}, {auth(m)})')
        m = lf_machine(text, svc=Lastfm(script=[None, lf_error(err)]))
        res = upload(m)
        if err == 9: continue   # (a scrobble's error 9 is the session: lastfm_session_tests)
        expect(res == (want, 0) and methods(m) == ['getMobileSession', 'scrobble'] and log_of(m) == text, f'track.scrobble answered error {err}: {want}, the log untouched ({res})')
        expect(lastfm(m)[0] == (LF_BAD if want == AUTH else LF_IN), f'error {err} to a scrobble: {"refused, the session dropped" if want == AUTH else "the session is kept"} ({lastfm(m)[0]})')
    for what, ans in (('HTTP 500 without a body', {'code': 500}), ('HTTP 503 with a page', {'code': 503, 'body': b'<html>Service Unavailable</html>'}), ('a timeout', {'rc': 28, 'code': 0}), ('no connection', {'rc': 7, 'code': 0}),
                      ('a certificate that does not verify', {'rc': 60, 'code': 0}), ('an error as a string of digits that is no known one', lf_error('16')), ('a 200 that is not the service\'s object', {'body': b'[1,2]'})):
        for script in ([ans], [None, ans]):
            m = lf_machine(text, svc=Lastfm(script=list(script)))
            res = upload(m)
            expect(res == (FAIL, 0) and log_of(m) == text and auth(m) == 0 and usable(m) == 1 and len(lf_reqs(m)) == len(script), f'{what}, to request {len(script)}: a failure to try again, the account stands ({res})')
    m = lf_machine(text, svc=Lastfm(script=[lf_error('4')]))
    expect(upload(m) == (AUTH, 0), 'an error number written as a string is read too')
    # an error with a status of 200 is still the error
    m = lf_machine(text, svc=Lastfm(script=[lf_error(10, code=200)]))
    expect(upload(m) == (AUTH, 0) and lastfm(m)[0] == LF_BAD, 'the error member counts whatever the HTTP status')
    # refused: what stands, and what ends it
    m = lf_machine(text, svc=Lastfm(auth=4))
    expect(upload(m) == (AUTH, 0) and lastfm(m) == (LF_BAD, b'rob') and configured(m) == 1 and usable(m) == 0, 'refused credentials: set up, not usable')
    forget(m)
    expect(lastfm(m)[0] == LF_BAD, 'the refusal follows the file: the same credentials read again are still refused')
    m.thread = None
    expect(start(m) == 1, 'a manual upload with nothing but refused accounts asks them again')
    work(m)
    expect(poll(m) == (AUTH, 0) and auth(m) == LF, 'and is refused again')
    m.fs[INI] = lf_ini(pw='fixed').encode(); forget(m)
    expect(lastfm(m)[0] == LF_NEW and usable(m) == 1, 'another password in the file: no longer refused')
    m.fs[INI] = lf_ini().encode(); forget(m)
    expect(lastfm(m)[0] == LF_BAD, 'the refused one put back: refused')
    m.lf.auth = None
    expect(lf_check(m) == (OK, 0) and lastfm(m)[0] == LF_IN and usable(m) == 1, 'a check the service accepts ends the refusal')
    m = lf_machine(text, svc=Lastfm(auth=4))
    expect(lf_check(m) == (AUTH, 0) and lastfm(m)[0] == LF_BAD and auth(m) == LF, 'a check the service refuses: refused')
    def during(i): m.fs[INI] = lf_ini(pw='changed meanwhile').encode()
    m = lf_machine(text, svc=Lastfm(auth=4)); m.site.during = during
    expect(upload(m) == (AUTH, 0) and lastfm(m)[0] == LF_NEW and auth(m) == LF, 'credentials changed while the refused request ran: the new ones are not marked')
    # the kill switch between the session and the batch
    def during(i): m.present.add(KILL)
    m = lf_machine(text); m.site.during = during
    expect(upload(m) == (FAIL, 0) and methods(m) == ['getMobileSession'] and log_of(m) == text, 'the kill switch appearing during the session request: no scrobble is sent')


def lastfm_ignored_tests(ctx):
    """track.scrobble's answer: a listen with an ignoredMessage code is refused for good (the daily limit apart), the others are taken."""
    expect = ctx.expect
    lines = [line(i) for i in range(10)]
    text = HEADER + ''.join(lines)
    m = lf_machine(text, svc=Lastfm(ignored={3: 1, 4: 3, 8: 2}))
    res = upload(m)
    expect(res == (OK, 7) and rejected(m) == 3 and len(lf_reqs(m)) == 2, f'three of ten ignored (the artist, a time too old, the track): 7 sent, 3 refused, in the one request ({res}, {rejected(m)})')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines[:3] + lines[5:8] + lines[9:]) and rej_of(m) == ''.join(lines[3:5] + lines[8:9]), f'the ignored ones leave the log for .rejected, the others for .sent ({rej_of(m)!r})')
    m = lf_machine(HEADER + line(0), svc=Lastfm(ignored={0: 4}))
    res = upload(m)
    expect(res == (OK, 0) and rejected(m) == 1 and log_of(m) == HEADER and rej_of(m) == line(0) and SENT not in m.fs, f'one listen (the answer has an object, no array), ignored: refused ({res})')
    m = lf_machine(text, svc=Lastfm(ignored={i: 1 for i in range(10)}))
    res = upload(m)
    expect(res == (OK, 0) and rejected(m) == 10 and rej_of(m) == ''.join(lines) and log_of(m) == HEADER, f'every listen ignored: all in .rejected ({res})')
    m = lf_machine(text, svc=Lastfm(ignored={2: 5}))
    res = upload(m)
    expect(res == (FAIL, 0) and log_of(m) == text and SENT not in m.fs and REJ not in m.fs and usable(m) == 1, f'a listen ignored for the daily limit (code 5) is not refused for good: a failure, the batch stays ({res})')
    for what, body in (('no scrobble member', {'scrobbles': {'@attr': {'accepted': 10, 'ignored': 0}}}), ('a shorter array', {'scrobbles': {'scrobble': [{'ignoredMessage': {'code': '0'}}] * 4}}),
                       ('entries without an ignoredMessage', {'scrobbles': {'scrobble': [{'timestamp': '1'}] * 10}}), ('codes as numbers', {'scrobbles': {'scrobble': [{'ignoredMessage': {'code': 0}}] * 10}})):
        m = lf_machine(text, svc=Lastfm(script=[None, {'body': json.dumps(body).encode()}]))
        res = upload(m)
        expect(res == (OK, 10) and rejected(m) == 0 and log_of(m) == HEADER, f'an accepted request with {what}: the listens it does not name as ignored are taken ({res})')
    m = lf_machine(text, svc=Lastfm(script=[None, {'body': json.dumps({'scrobbles': {'scrobble': [{'ignoredMessage': {'code': 1}}] + [{'ignoredMessage': {'code': '0'}}] * 9}}).encode()}]))
    expect(upload(m) == (OK, 9) and rej_of(m) == lines[0], 'a code written as a number is read too')
    m = lf_machine(text, svc=Lastfm(script=[None, {'body': b'{"status":"ok"}'}]))
    expect(upload(m) == (FAIL, 0) and log_of(m) == text, 'a 200 without the scrobbles object is no answer: a failure')
    # skipped lines go with the listens around them
    text2 = HEADER + lines[0] + 'junk\n' + lines[1] + '# note\n' + lines[2]
    m = lf_machine(text2, svc=Lastfm(ignored={1: 1}))
    expect(upload(m) == (OK, 2) and rej_of(m) == 'junk\n' + lines[1] and sent_of(m) == lines[0] + lines[2] and log_of(m) == HEADER, 'a skipped line goes with the listen after it; comments are dropped')


def both_tests(ctx):
    """Two services, one log: a listen leaves once each service that is set up took it or refused it for good; .sent when one took it, .rejected when all refused it; a service that
    stands refused is left out."""
    expect = ctx.expect
    lines = [line(i) for i in range(6)]
    text = HEADER + ''.join(lines)
    m = lf_machine(text, lb=True)
    res = upload(m)
    expect(res == (OK, 6) and lb_stamps(m) == [list(range(6))] and lf_stamps(m) == [list(range(6))] and [r['url'] for r in m.site.reqs] == [URL, LF_URL, LF_URL], f'both set up: the batch goes to ListenBrainz, then to Last.fm ({res}, {[r["url"] for r in m.site.reqs]})')
    expect(lb_reqs(m)[0]['heads'] == ['Authorization: Token ' + TOKEN, 'Content-Type: application/json'] and lf_reqs(m)[0]['heads'] == ['Content-Type: application/x-www-form-urlencoded'] and TOKEN.encode() not in b''.join(r['body'] for r in lf_reqs(m)),
           'each with its own account: the token is not sent to Last.fm')
    expect(log_of(m) == HEADER and sent_of(m) == ''.join(lines) and REJ not in m.fs and auth(m) == 0 and lastfm(m)[0] == LF_IN and invalid(m) == 0, 'all six in .sent')
    # the matrix: 1 refused by ListenBrainz only, 2 by Last.fm only, 4 by both
    m = lf_machine(text, lb=True, svc=Lastfm(lb=judge(bad=(1, 4)), ignored={2: 1, 4: 2}))
    res = upload(m)
    expect(res == (OK, 5) and rejected(m) == 1, f'one listen refused by ListenBrainz alone, one by Last.fm alone, one by both: 5 sent, 1 refused ({res}, {rejected(m)})')
    expect(sent_of(m) == ''.join(lines[:4] + lines[5:]) and rej_of(m) == lines[4] and log_of(m) == HEADER, f'a listen one service took is in .sent; only the one both refused is in .rejected ({rej_of(m)!r})')
    expect(lb_stamps(m) == [list(range(6))] + [[i] for i in range(6)] and lf_stamps(m) == [list(range(6))], f'ListenBrainz narrows its 400 one listen a request; Last.fm gets the batch once ({lb_stamps(m)})')
    # one service fails for now: the batch stays for both
    for what, svc, lbn, lfn in (('Last.fm answers error 16', Lastfm(script=[None, lf_error(16)]), 1, 1), ('Last.fm gives no session', Lastfm(script=[{'code': 500}]), 1, 0), ('Last.fm does not answer', Lastfm(script=[None, {'rc': 28, 'code': 0}]), 1, 1),
                                ('ListenBrainz answers 500', Lastfm(lb={'code': 500}), 1, 0), ('ListenBrainz answers 429', Lastfm(lb={'code': 429}), 1, 0)):
        m = lf_machine(text, lb=True, svc=svc); m.log = []
        res = upload(m)
        expect(res == (FAIL, 0) and log_of(m) == text and SENT not in m.fs and REJ not in m.fs and not wrote(m), f'{what}: a failure, nothing leaves the log, though the other service took the batch ({res})')
        expect((len(lb_stamps(m)), len(lf_stamps(m))) == (lbn, lfn) and auth(m) == 0, f'{what}: {lbn} ListenBrainz and {lfn} Last.fm batches were sent ({len(lb_stamps(m))}, {len(lf_stamps(m))})')
        m.lf.script, m.lf.lb = [], None
        res = upload(m)
        expect(res == (OK, 6) and lb_stamps(m)[-1] == list(range(6)) and lf_stamps(m)[-1] == list(range(6)) and log_of(m) == HEADER and sent_of(m) == ''.join(lines), f'{what}: the next upload sends the batch to both again ({res})')
    # a second batch that fails at Last.fm: the first is retired
    many = [line(i) for i in range(60)]
    m = lf_machine(HEADER + ''.join(many), lb=True, svc=Lastfm(script=[None, None, lf_error(29)]))
    res = upload(m)
    expect(res == (FAIL, 50) and log_of(m) == HEADER + ''.join(many[50:]) and sent_of(m) == ''.join(many[:50]) and lb_stamps(m) == [list(range(50)), list(range(50, 60))], f'the second batch fails at Last.fm: the first 50 are archived, the 10 stay for both ({res})')
    # narrowing cut short by a failure, then Last.fm never asked: nothing of the batch leaves
    m = lf_machine(text, lb=True, svc=Lastfm(lb=judge(bad=(1,), alone={3: {'code': 500}})))
    res = upload(m)
    expect(res == (FAIL, 0) and log_of(m) == text and not lf_reqs(m), f'ListenBrainz fails while it narrows: Last.fm has not seen the batch, so none of it leaves ({res})')
    # Last.fm refuses its account: the upload ends, the next one leaves it out
    m = lf_machine(text, lb=True, svc=Lastfm(auth=4))
    res = upload(m)
    expect(res == (AUTH, 0) and auth(m) == LF and log_of(m) == text and lastfm(m)[0] == LF_BAD and invalid(m) == 0 and usable(m) == 1, f'Last.fm refuses the credentials: the upload ends as refused, scrobup_auth names Last.fm, ListenBrainz stands ({res}, {auth(m)})')
    n = len(m.site.reqs)
    res = upload(m)
    expect(res == (OK, 6) and [r['url'] for r in m.site.reqs[n:]] == [URL] and log_of(m) == HEADER and sent_of(m) == ''.join(lines), f'the next upload goes to ListenBrainz alone, and the listens leave: a refused service does not hold the log ({res})')
    expect(auth(m) == LF and lastfm(m)[0] == LF_BAD, 'its result still names Last.fm as refused (left out)')
    m.fs[INI] = (ini(name='rob') + lf_ini(pw='fixed')).encode(); m.lf.auth = None; m.fs[LOG] += line(9).encode(); n = len(m.site.reqs)
    res = upload(m)
    expect(res == (OK, 1) and [r['url'] for r in m.site.reqs[n:]] == [URL, LF_URL, LF_URL] and auth(m) == 0 and lastfm(m)[0] == LF_IN, f'other credentials in the file: Last.fm takes part again ({res})')
    # ListenBrainz refuses its token: the same, the other way round
    m = lf_machine(text, lb=True, svc=Lastfm(lb={'code': 401}))
    res = upload(m)
    expect(res == (AUTH, 0) and auth(m) == LB and invalid(m) == 1 and lastfm(m)[0] == LF_NEW and usable(m) == 1 and not lf_reqs(m) and log_of(m) == text, f'ListenBrainz refuses the token: Invalid Token, Last.fm stands ({res}, {auth(m)})')
    res = upload(m)
    expect(res == (OK, 6) and len(lb_reqs(m)) == 1 and lf_stamps(m) == [list(range(6))] and log_of(m) == HEADER and auth(m) == LB and invalid(m) == 1, f'the next upload goes to Last.fm alone; the token is still Invalid Token ({res})')
    # both refused: asked again
    m = lf_machine(text, lb=True, svc=Lastfm(lb={'code': 401}, auth=10))
    expect(upload(m) == (AUTH, 0) and upload(m) == (AUTH, 0) and auth(m) == LB | LF and invalid(m) == 1 and lastfm(m)[0] == LF_BAD and usable(m) == 0 and configured(m) == 1, 'both refused, one after the other: nothing usable')
    n = len(m.site.reqs)
    expect(upload(m) == (AUTH, 0) and [r['url'] for r in m.site.reqs[n:]] == [URL] and auth(m) == LB, 'a manual upload then asks them again, ListenBrainz first')
    # the ListenBrainz check beside a Last.fm section
    m = lf_machine(text, raw=(ini() + lf_ini()).encode(), svc=Lastfm(lb=answer('rob')))
    expect(check(m) == (OK, 0) and ini_of(m) == (ini(name='rob') + lf_ini()).encode() and [r['url'] for r in m.site.reqs] == [CHECK_URL] and lastfm(m)[0] == LF_NEW, 'validate-token writes USER into its own section; Last.fm is not asked and its section is untouched')
    # no memory for Last.fm's answer
    m = lf_machine(text, lb=True); m.calloc_fail_size = BODY
    expect(upload(m) == (FAIL, 0) and not m.site.reqs and log_of(m) == text, 'no memory in the thread: a failure, nothing sent')
    # ListenBrainz alone is as before: no Last.fm request, no answer buffer
    m = machine(text); m.log = []
    expect(upload(m) == (OK, 6) and not lf_reqs(m) and auth(m) == 0 and lastfm(m)[0] == LF_NONE and [c[1] for c in m.log if c[0] == 'calloc'].count(BODY) == 1, 'with no [LASTFM] section nothing of Last.fm runs')


SECTIONS = [upload_tests, skip_tests, nothing_tests, fail_tests, append_tests, disk_tests, start_tests, account_tests, ini_tests, edit_tests, check_tests, exclusive_tests, reject_tests, narrow_tests, owner_tests, kill_tests, files_tests,
            lastfm_ini_tests, lastfm_sign_tests, lastfm_session_tests, lastfm_error_tests, lastfm_ignored_tests, both_tests]
