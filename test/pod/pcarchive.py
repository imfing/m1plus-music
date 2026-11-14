"""See All (docs/modules/podcasts.md "All episodes"): the archive job (patch/pcnet.c, pn_arch_*: the feed fetched again with every item written to .archive through the parser's sink),
the merged model (pc_load_show with an archive: the union of .episodes and .archive, an episode once, the newest PC_ALL_MAX, either order), a download of an archive-only episode and the Show page's
row (patch/podcasts.c). The compiled payload runs under Unicorn against a scripted libcurl."""
import email.utils
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

PCN = sibling('pcnet')
PCP = PCN.PCP
PSH = sibling('pcshow')
DL = PSH.DL
RD, PN = PCN.ROOT_DIR, dict(PCN.PN, CANCELLED=12)
ARCH_MAX, ARCH_BYTES = 2000, 1572864
AR = dict(IDLE=0, RUNNING=1, DONE=2, FAILED=3)
BASE = 1_700_000_000
DAY = 86400


def item(i, desc=None, url=None, title=None, day=None):
    d = email.utils.formatdate(BASE + (day if day is not None else i) * DAY, usegmt=True)
    return (f'<item><title>{title or f"Ep {i}"}</title><guid>g{i}</guid><pubDate>{d}</pubDate><description>{desc or f"About {i}"}</description>'
            f'<enclosure url="{url or f"https://cdn.example/e{i}.mp3"}" length="1000" type="audio/mpeg"/></item>')


def feed(items):
    """A feed that lists its items newest first, as feeds do."""
    return ('<?xml version="1.0"?><rss version="2.0"><channel><title>Show</title>' + ''.join(items) + '</channel></rss>').encode()


def lines_of(data):
    """The entries of an .episodes / .archive text: (header, [dict of key=value])."""
    text = data.decode('utf-8').split('\n')
    return text[0], [dict(f.split('=', 1) for f in ln.split('\t')) for ln in text[1:] if ln]


def show_addr(m, folder):
    shows, arr = m.shows()
    return arr + next(i for i, s in enumerate(shows) if s['dir'] == folder) * O['PC_SHOW_SIZE']


def start(m, folder='A'):
    m.thread = None
    r = m.call(PSYMS['pn_arch_start'], a0=m.cstr(RD), a1=show_addr(m, folder), count=1 << 40)
    return r, m.thread


def state(m): return m.call(PSYMS['pn_arch_state'], count=2000), m.call(PSYMS['pn_arch_code'], count=2000)


def run_job(m, body_or_site, folder='A'):
    m.curl_site = body_or_site if callable(body_or_site) else (lambda url, o: {'body': body_or_site})
    r, th = start(m, folder)
    assert r == 0 and th and th[0] == PSYMS['pn_armain'], (r, th)
    PCN.work(m, th)
    m.slept = [c[1] for c in m.calls if c[0] == 'sleep']   # (the waits of the worker's run: the state calls below start new call logs)
    return state(m)


def eps_text(*entries):
    return (PCP.EPS_HEAD + ''.join('\t'.join(f'{k}={v}' for k, v in e.items()) + '\n' for e in entries)).encode()


def job_tests(ctx):
    expect = ctx.expect
    F = 'https://feeds.example/a'
    # 1. Every item is written, with the names the refresh would give; .episodes is not touched; the state and the generation say so
    m = PCN.machine()
    PCN.sub(m, 'A', F)
    old = eps_text(dict(g='g3', p=BASE + 3 * DAY, d=60, l=1000, f='kept name.mp3', t='Ep 3', u='https://cdn.example/e3.mp3', x='old desc'))
    m.put(f'{RD}/A/.episodes', old)
    items = [item(i) for i in range(29, -1, -1)] + [item(100, title='Same', day=500), item(101, title='Same', day=500)]
    g0 = m.call(PSYMS['pn_gen'], count=2000)
    r, th = start(m)
    expect(r == 0 and th and th[0] == PSYMS['pn_armain'] and state(m) == (AR['RUNNING'], 0) and m.call(PSYMS['pn_busy'], count=2000) == 0 and m.call(PSYMS['pn_job_busy'], count=2000) == 1
           and m.call(PSYMS['pn_arch_hash'], count=2000) == PCN.pc_hash('A'), 'the job runs on the worker: running, a job (not a refresh), of that show')
    r2 = m.call(PSYMS['pn_arch_start'], a0=m.cstr(RD), a1=show_addr(m, 'A'), count=1 << 40)
    expect(r2 == PN['BUSY'], 'a second start while it runs: PN_BUSY')
    sites = []
    m.curl_site = lambda url, o: (sites.append((url, dict(o))), {'body': feed(items)})[1]
    PCN.work(m, th)
    expect(state(m) == (AR['DONE'], 0) and m.call(PSYMS['pn_gen'], count=2000) > g0 and not m.call(PSYMS['pn_job_busy'], count=2000), 'done: state, generation moved, the slot is free')
    expect([u for u, _ in sites] == [F] and sites[0][1][10065] == PCN.CA and sites[0][1][13] == 300, 'one request for the feed, certificates verified, a 300 s limit for a long feed')
    data = m.fs.get(f'{RD}/A/.archive')
    head, rows = lines_of(data)
    expect(head == 'M1PLUS-EPISODES 1' and len(rows) == 32 and [r['g'] for r in rows[:3]] == ['g29', 'g28', 'g27'] and {f'{RD}/A/.archive.tmp'} - set(m.fs) == {f'{RD}/A/.archive.tmp'},
           f'every item, in the feed\'s order ({len(rows)} lines), no temp file left')
    by = {r['g']: r for r in rows}
    expect(by['g3']['f'] == 'kept name.mp3' and by['g3'].get('x') == 'About 3' and by['g4']['f'].endswith('Ep 4.mp3') and by['g4']['u'] == 'https://cdn.example/e4.mp3' and int(by['g4']['p']) == BASE + 4 * DAY,
           'an item .episodes has keeps its file name; the others are named as a refresh names them')
    expect(by['g100']['f'] != by['g101']['f'] and by['g101']['f'].endswith('Same (2).mp3'), 'two items of one day and one title: the second is numbered')
    expect(m.fs.get(f'{RD}/A/.episodes') == old, 'the job never writes .episodes')
    m.call(PSYMS['pn_arch_reset'], count=2000)
    expect(state(m) == (AR['IDLE'], 0), 'reset forgets a finished job')

    # 2. A feed with a few items gives a few; a feed with none, an HTML page, a 404 and a card that is full give no archive and say why
    m = PCN.machine(); PCN.sub(m, 'A', F)
    expect(run_job(m, feed([item(i) for i in (2, 1, 0)])) == (AR['DONE'], 0) and len(lines_of(m.fs[f'{RD}/A/.archive'])[1]) == 3, 'a feed with three items: three lines, no error')
    for what, site, code in (('no item', feed([]), PN['NOTFEED']), ('an HTML page', b'<html><body>hi</body></html>', PN['NOTFEED']), ('a 404', lambda u, o: {'rc': 22, 'code': 404}, PN['GONE']),
                             ('a network error', lambda u, o: {'rc': 6}, PN['NET'])):
        m = PCN.machine(); PCN.sub(m, 'A', F)
        st = run_job(m, site)
        expect(st == (AR['FAILED'], code) and f'{RD}/A/.archive' not in m.fs and f'{RD}/A/.archive.tmp' not in m.fs, f'{what}: failed with PN code {code}, no .archive and no temp file ({st})')
    m = PCN.machine(); PCN.sub(m, 'A', F)
    m.curl_site = lambda url, o: {'body': feed([item(1)])}
    r, th = start(m)
    m.card_mounted = False
    PCN.work(m, th)
    expect(state(m)[0] == AR['FAILED'] and f'{RD}/A/.archive' not in m.fs, 'the card removed before the end: failed, nothing renamed into place')
    m = PCN.machine(); PCN.sub(m, 'A', '')
    r = m.call(PSYMS['pn_arch_start'], a0=m.cstr(RD), a1=show_addr(m, 'A'), count=1 << 40)
    expect(r == 16, 'a show with no feed address does not start')
    m = PCN.machine(ca=False); PCN.sub(m, 'A', F)
    r = m.call(PSYMS['pn_arch_start'], a0=m.cstr(RD), a1=show_addr(m, 'A'), count=1 << 40)
    expect(r == PN['NOCERT'], 'the guards apply (no certificate bundle)')

    # 3. The caps: 2000 items and 1.5 MiB
    m = PCN.machine(); PCN.sub(m, 'A', F)
    st = run_job(m, feed([item(i) for i in range(2100, 0, -1)]))
    _, rows = lines_of(m.fs[f'{RD}/A/.archive'])
    expect(st == (AR['DONE'], 0) and len(rows) == ARCH_MAX and rows[0]['g'] == 'g2100', f'a feed of 2100 items: the first {ARCH_MAX} (the newest, as feeds list them) and no error ({len(rows)})')
    m = PCN.machine(); PCN.sub(m, 'A', F)
    long_url = 'https://cdn.example/' + 'x' * 600 + '/{}.mp3'
    st = run_job(m, feed([item(i, desc='d' * 190, url=long_url.format(i), title='T' * 90) for i in range(1900, 0, -1)]))
    data = m.fs[f'{RD}/A/.archive']
    _, rows = lines_of(data)
    expect(st == (AR['DONE'], 0) and len(data) <= ARCH_BYTES and len(data) > ARCH_BYTES - 1500 and len(rows) < 1900 and rows[-1]['g'] == f'g{1900 - len(rows) + 1}',
           f'long items (about 900 bytes a line): the file stops at {ARCH_BYTES} bytes, whole lines ({len(data)} bytes, {len(rows)} lines)')


def episodes(m, addr, mx=300, all=True):
    """pc_load_show_all (all=False: pc_load_show, the recent list) into a block of the emulated heap (the harness's scratch area is too small for 2000 records)."""
    out = m.malloc(mx * O['PC_EP_SIZE'])
    n = m.call(PSYMS['pc_load_show_all' if all else 'pc_load_show'], a0=addr, a1=out, a2=mx, count=1 << 40)
    return [m.ep(out + i * O['PC_EP_SIZE']) for i in range(n)]


def model_tests(ctx):
    expect = ctx.expect
    m = PCN.machine(); m.reuse_heap = True; PCN.sub(m, 'A', 'https://feeds.example/a')
    m.put(f'{RD}/A/a.mp3', b'x')
    m.put(f'{RD}/A/.episodes', eps_text(dict(g='g1', p=1000, f='a.mp3', t='One', u='u1'), dict(g='g2', p=2000, f='b.mp3', t='Two', u='u2')))
    addr = show_addr(m, 'A')
    expect(m.call(PSYMS['pc_has_archive'], a0=addr, count=2000000) == 0 and m.call(PSYMS['pc_all_cap'], a0=addr, count=2000000) == 700 and [e['title'] for e in episodes(m, addr)] == ['Two', 'One'],
           'no archive: room for 300 entries and 400 files, the list as before')
    m.put(f'{RD}/A/.archive', eps_text(dict(g='g4', p=3000, f='d.mp3', t='Four', u='u4'), dict(g='g1', p=1000, f='other.mp3', t='One again', u='u1'), dict(g='g2', p=2000, f='b.mp3', t='Two again', u='u2'),
                                       dict(g='g3', p=500, f='c.mp3', t='Three', u='u3'), dict(p=100, f='a.mp3', t='No guid, a file .episodes has', u='u9'), dict(p=50, f='e.mp3', t='No guid, new', u='u5')))
    expect(m.call(PSYMS['pc_has_archive'], a0=addr, count=2000000) == 1 and m.call(PSYMS['pc_all_cap'], a0=addr, count=2000000) == 2700, 'with an archive: room for 2700 (the 300 entries of .episodes and the 2400 files scanned)')
    got = episodes(m, addr, ARCH_MAX)
    expect([e['title'] for e in got] == ['Four', 'Two', 'One', 'Three', 'No guid, new'], f'the union, an episode once (guid, or the file name when there is no guid), the .episodes entry winning, newest first ({[e["title"] for e in got]})')
    expect([e['file'] for e in got][2] == 'a.mp3' and got[2]['title'] == 'One', 'the .episodes entry wins (its file, its title), not the archive\'s copy')
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=1, count=2000000)
    shows, arr = m.shows()
    got = episodes(m, addr, ARCH_MAX)
    expect([e['title'] for e in got] == ['No guid, new', 'Three', 'One', 'Two', 'Four'], 'Oldest First: the exact reverse')
    expect([e['title'] for e in episodes(m, addr, 3)] == ['One', 'Two', 'Four'], 'a smaller max keeps the newest under either order (Oldest First lists them oldest first)')
    # the caps: 2000 of an archive of 2100
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=0, count=2000000)
    m.put(f'{RD}/A/.archive', eps_text(*[dict(g=f'x{i}', p=10000 + i, f=f'x{i}.mp3', t=f'X {i}', u=f'u{i}') for i in range(2099, -1, -1)]))   # (as the job writes it: the feed's order, newest first)
    got = episodes(m, addr, ARCH_MAX)
    expect(len(got) == ARCH_MAX and got[0]['title'] == 'X 2099' and got[-2]['title'] == 'X 101' and got[-1]['title'] == 'One' and got[-1]['state'] == O['PC_LOCAL'],
           f'an archive of 2100 in a room of {ARCH_MAX}: the newest, and the downloaded file (older than them all) before the oldest that is only in the feed ({len(got)}, {got[0]["title"]} to {got[-2]["title"]}, {got[-1]["title"]})')
    got = episodes(m, addr, 300)
    expect(len(got) == 300 and got[0]['title'] == 'X 2099', 'a caller with room for 300 gets the newest 300')
    # a show with no .episodes at all but an archive (the .episodes is the refresh's: a missing one cannot happen after a refresh, but the list must not break)
    m.fs.pop(f'{RD}/A/.episodes'); m.fs.pop(f'{RD}/A/a.mp3')
    m.put(f'{RD}/A/.archive', eps_text(dict(g='y1', p=5, f='y1.mp3', t='Y1', u='u')))
    expect([e['title'] for e in episodes(m, addr, ARCH_MAX)] == ['Y1'], 'an archive and no .episodes: the archive\'s entries')
    # more files than a show without an archive may have (400): every downloaded episode of the archive is on the card for the model
    m.put(f'{RD}/A/.archive', eps_text(*[dict(g=f'w{i}', p=20000 + i, f=f'w{i}.mp3', t=f'W {i}', u=f'u{i}') for i in range(519, -1, -1)]))
    for i in range(520): m.put(f'{RD}/A/w{i}.mp3', b'x')
    for i in range(30): m.put(f'{RD}/A/copied{i}.mp3', b'x')   # files no entry names: episodes of their own
    got = episodes(m, addr, ARCH_MAX)
    local = [e for e in got if e['state'] == O['PC_LOCAL']]
    expect(len(got) == 550 and len(local) == 550 and all(e['hash'] for e in got), f'520 downloaded episodes of an archive and 30 copied files: all on the card ({len(got)} episodes, {len(local)} local)')


def recent_tests(ctx):
    """pc_load_show is the recent list: .episodes and the files on the card, never the archive's other entries; a file (or .part) no .episodes entry names is looked up in .archive for its title, date and description, and
    .archive is read only then. pc_load_show_all is the union; pc_count_all counts it."""
    expect = ctx.expect
    m = PCN.machine(); m.reuse_heap = True; PCN.sub(m, 'A', 'https://feeds.example/a')
    m.put(f'{RD}/A/a.mp3', b'x')
    m.put(f'{RD}/A/.episodes', eps_text(dict(g='g1', p=1000, f='a.mp3', t='One', u='u1'), dict(g='g2', p=2000, f='b.mp3', t='Two', u='u2')))
    addr = show_addr(m, 'A')
    m.put(f'{RD}/A/.archive', eps_text(dict(g='g4', p=3000, l=5, f='d.mp3', t='Four', u='u4', x='four desc'), dict(g='g1', p=1000, f='a.mp3', t='One', u='u1'), dict(g='g2', p=2000, f='b.mp3', t='Two', u='u2'),
                                       dict(g='g3', p=500, f='c.mp3', t='Three', u='u3'), dict(g='g5', p=100, f='e.mp3', t='Five', u='u5')))
    m.calls = []
    got = episodes(m, addr, all=False)
    expect([e['title'] for e in got] == ['Two', 'One'] and not reads_of(m, '.archive'), f'the recent list is .episodes and the files: the archive\'s other entries are not in it and .archive is not opened ({[e["title"] for e in got]})')
    expect([e['title'] for e in episodes(m, addr)] == ['Four', 'Two', 'One', 'Three', 'Five'] and m.call(PSYMS['pc_count_all'], a0=addr, count=1 << 40) == 5, 'the complete list has all five, and pc_count_all says so')
    m.put(f'{RD}/A/d.mp3', b'x')            # downloaded from the complete list: no .episodes entry names it
    m.put(f'{RD}/A/c.mp3.part', b'half')    # a download under way, the same
    m.calls = []
    got = episodes(m, addr, all=False)
    by = {e['title']: e for e in got}
    expect([e['title'] for e in got] == ['Four', 'Two', 'One', 'Three'] and reads_of(m, '.archive'), f'a file only the archive lists is in the recent list under its title, its .part too; the archive was read for them ({[e["title"] for e in got]})')
    expect(by['Four']['state'] == O['PC_LOCAL'] and by['Four']['pub'] == 3000 and by['Four']['file'] == 'd.mp3' and by['Four']['desc'] == 'four desc' and by['Four']['hash'] and by['Three']['state'] == O['PC_PART'],
           'its date, file and description come from the archive, it is PC_LOCAL (the .part PC_PART)')
    expect(len(episodes(m, addr, all=True)) == 5, 'the complete list is as it was (the file matches its archive entry once)')
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=1, count=2000000)
    expect([e['title'] for e in episodes(m, addr, all=False)] == ['Three', 'One', 'Two', 'Four'], 'Oldest First: the exact reverse')
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=0, count=2000000)
    # an entry .episodes has wins over a copy in the archive: no second row for its file
    m.put(f'{RD}/A/b.mp3', b'x')
    got = episodes(m, addr, all=False)
    expect([e['title'] for e in got].count('Two') == 1 and len(got) == 4, 'a file .episodes names is never looked up in the archive')
    # a show with no .episodes at all and an archive: the files are looked up in it
    m.fs.pop(f'{RD}/A/.episodes')
    got = episodes(m, addr, all=False)
    expect([e['title'] for e in got] == ['Four', 'Two', 'One', 'Three'], f'no .episodes: the recent list is the files (looked up in the archive where it has them) ({[e["title"] for e in got]})')
    # 520 downloaded episodes of the archive: every one is a local file of the recent list (the file scan is PM_ARCH_FILES long) up to the room the caller gave
    m = PCN.machine(); m.reuse_heap = True; PCN.sub(m, 'A', 'https://feeds.example/a'); addr = show_addr(m, 'A')
    m.put(f'{RD}/A/.episodes', eps_text(dict(g='g1', p=1000, f='a.mp3', t='One', u='u1')))
    m.put(f'{RD}/A/.archive', eps_text(*[dict(g=f'w{i}', p=20000 + i, f=f'w{i}.mp3', t=f'W {i}', u=f'u{i}') for i in range(519, -1, -1)]))
    for i in range(520): m.put(f'{RD}/A/w{i}.mp3', b'x')
    got = episodes(m, addr, ARCH_MAX, all=False)
    expect(len(got) == 521 and all(e['state'] == O['PC_LOCAL'] and e['title'].startswith('W') or e['title'] == 'One' for e in got), f'520 downloaded archive episodes: all of them are in the recent list with their titles ({len(got)})')


def fit(m, addr, all):
    """pc_load_fit: the list the pages and readers get (a block of its own size); all: the complete one."""
    cnt = m.malloc(4)
    out = m.call(PSYMS['pc_load_fit'], a0=addr, a1=cnt, a2=all, count=1 << 40)
    return [m.ep(out + i * O['PC_EP_SIZE']) for i in range(m.word(cnt))] if out else None


def recent(m, addr): return fit(m, addr, 0)


def keep_tests(ctx):
    """No file on the card is left out of a list for a newer episode that is not downloaded: the lists have room for every file (pc_all_cap), and a list that must be cut keeps the episodes with a file first.
    The case of the review: 20 episodes of the feed, none downloaded, and 281 older files gave 300 rows, the oldest file gone from Downloaded, Saved, Continue Listening and the iPod level."""
    expect = ctx.expect
    remote = [dict(g=f'r{i}', p=900000 + i, f=f'r{i}.mp3', t=f'R {i}', u=f'u{i}') for i in range(19, -1, -1)]
    def card(n_files, arch=False):
        m = PCN.machine(); m.reuse_heap = True; PCN.sub(m, 'A', 'https://feeds.example/a')
        m.put(f'{RD}/A/.episodes', eps_text(*remote))
        for i in range(n_files): m.put(f'{RD}/A/old{i:04d}.mp3', b'x', mtime=1000 + i)
        if arch: m.put(f'{RD}/A/.archive', eps_text(*remote))
        return m, show_addr(m, 'A')
    local = lambda got: sorted(e['file'] for e in got if e['state'] == O['PC_LOCAL'])
    files = lambda n: sorted(f'old{i:04d}.mp3' for i in range(n))
    m, addr = card(281)
    got = recent(m, addr)
    expect(m.call(PSYMS['pc_all_cap'], a0=addr, count=2000000) == 700, 'no archive: room for the 300 entries of .episodes and the 400 files a folder is scanned for')
    expect(got is not None and len(got) == 301 and local(got) == files(281) and [e['title'] for e in got[:20]] == [f'R {i}' for i in range(19, -1, -1)],
           f'20 episodes of the feed and 281 older files: all 301 are listed, every file among them, the oldest too ({len(got or [])} rows, {len(local(got or []))} files)')
    # a smaller room than pc_all_cap (no caller gives one): the episodes that are only in the feed keep their places (up to PC_MAX_EPS, half the room at most), then the files, the newest of each
    cut = episodes(m, addr, 300, all=False)
    expect(len(cut) == 300 and [e['title'] for e in cut[:20]] == [f'R {i}' for i in range(19, -1, -1)] and local(cut) == files(281)[1:],
           f'room for 300: the 20 of the feed and the 280 newest files ({len(local(cut))} files, the oldest {local(cut)[:1]})')
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=1, count=2000000)
    old = episodes(m, addr, 300, all=False)
    expect([e['file'] for e in old] == [e['file'] for e in cut][::-1], 'Oldest First: the same 300 episodes, the exact reverse')
    m.call(PSYMS['pc_order_set'], a0=PCN.pc_hash('A'), a1=0, count=2000000)
    few = episodes(m, addr, 30, all=False)
    expect(len(few) == 30 and [e['title'] for e in few[:15]] == [f'R {i}' for i in range(19, 4, -1)] and local(few) == files(281)[-15:],
           f'room for 30: half for the newest of the feed, half for the newest files ({[e["title"] for e in few[:1]]}, {len(local(few))} files)')
    m, addr = card(400)
    got = recent(m, addr)
    expect(len(got) == 420 and local(got) == files(400), f'the 400 files a folder is scanned for and the 20 of the feed: none is cut ({len(got)})')
    # a show with an archive: the files beyond 300 are in the recent list too (the archive names none of them: they are copied files)
    m, addr = card(350, arch=True)
    got = recent(m, addr)
    expect(len(got) == 370 and local(got) == files(350), f'with an archive: 350 files and the 20 of the feed are all in the recent list ({len(got)})')
    # the second review's case: every one of an archive's 2000 episodes is downloaded, then a refresh finds new ones. The files must not take every place: the new episodes are listed (the first is Latest Episode)
    m = PCN.machine(); m.reuse_heap = True; PCN.sub(m, 'A', 'https://feeds.example/a'); addr = show_addr(m, 'A')
    new = [dict(g=f'n{i}', p=900000 + i, f=f'n{i}.mp3', t=f'New {i}', u=f'v{i}') for i in range(4, -1, -1)]
    arch = [dict(g=f'w{i}', p=20000 + i, f=f'w{i:04d}.mp3', t=f'W {i}', u=f'u{i}') for i in range(ARCH_MAX - 1, -1, -1)]
    m.put(f'{RD}/A/.episodes', eps_text(*new))
    m.put(f'{RD}/A/.archive', eps_text(*(new + arch)[:ARCH_MAX]))   # (the refresh merged the new ones in: the five oldest lines left the archive, their files are still on the card)
    for i in range(ARCH_MAX): m.put(f'{RD}/A/w{i:04d}.mp3', b'x', mtime=20000 + i)
    every = sorted(f'w{i:04d}.mp3' for i in range(ARCH_MAX))
    expect(m.call(PSYMS['pc_all_cap'], a0=addr, count=2000000) == 2700, 'with an archive: room for the 300 entries of .episodes and the 2400 files a folder is scanned for')
    for name, got in (('recent', recent(m, addr)), ('complete', fit(m, addr, 1))):
        expect(got is not None and len(got) == ARCH_MAX + 5 and [e['title'] for e in got[:5]] == [f'New {i}' for i in range(4, -1, -1)] and got[0]['state'] == O['PC_REMOTE'] and local(got) == every,
               f'2000 downloaded episodes and five new ones, the {name} list: the new ones first, every file after them ({len(got or [])} rows, {[e["title"] for e in (got or [])[:1]]}, {len(local(got or []))} files)')
    expect(m.call(PSYMS['pc_count_all'], a0=addr, count=1 << 40) == ARCH_MAX + 5, 'See All counts them all')
    cut = episodes(m, addr, ARCH_MAX)
    expect(len(cut) == ARCH_MAX and [e['title'] for e in cut[:5]] == [f'New {i}' for i in range(4, -1, -1)] and local(cut) == every[5:],
           f'a room of 2000 (smaller than any caller gives): the five new episodes are kept and the five oldest files go ({[e["title"] for e in cut[:1]]}, {len(local(cut))} files)')


def reads_of(m, name): return [c for c in m.calls if c[0] in ('open', 'fopen') and isinstance(c[1], str) and c[1].endswith(name)]


def markall_tests(ctx):
    """Mark All as Played on a list longer than the old ring (512 places): every mark is kept, the places of other shows too, and the ring is written once."""
    expect = ctx.expect
    RP, DEEP = PSH.RP, PSH.DEEP
    N = 520

    def card(mm):
        PSH.deep_card(mm)
        mm.put(f'{RP}/{DEEP}/.archive', eps_text(*[dict(g=f'z{i}', p=1000 + i, f=f'z{i}.mp3', t=f'Z {i}', u=f'https://cdn.example/z{i}.mp3') for i in range(N - 1, -1, -1)]))
    m = PSH.machine(card=card); PSH.open_show(m)
    PCP.tap(m, 150, PCP.hdr(m) + 8 * PCP.CELL + O['PS_MORE_H'] // 2, off=max(0, m.props[(m.sv, 'virtual_h')] - 400))   # (See All (528): the page with every episode)
    other = PCP.pc_hash(f'{RP}/Alpha Show/ep1.mp3')
    m.call(PSYMS['pc_mark'], a0=other, a1=1, count=2000000)   # (another show's mark, the ring's oldest slot after the marks below)
    h_z = lambda i: PCP.pc_hash(f'{RP}/{DEEP}/z{i}.mp3')
    RING = sibling('podcasts').RING
    before = m.fs.get(RING)
    PCP.click(m, 'btn_more')
    m.calls = []
    PCP.click(m, 'pg_sh_markall')
    writes = [c for c in m.calls if c[0] == 'rename' and c[2] == RING]
    st = [m.state(h_z(i))[0] for i in range(N)]
    expect(all(s == 2 for s in st), f'{N} episodes of an archive: every one is played after Mark All as Played on the All Episodes page ({st.count(2)} of {N})')
    expect(m.state(other)[0] == 2, 'the mark another show had is kept')
    expect(m.fs.get(RING) != before and len(writes) == 1, f'the ring is written once, not once a mark ({len(writes)} renames)')
    expect(O['PC_RING_SLOTS'] >= 2 * ARCH_MAX, 'the ring holds two lists of the longest show')


def refresh_tests(ctx):
    """A refresh writes the newest 20 into .episodes as before and merges the items its archive lacks into .archive (no full fetch): newest first, no duplicates, at most 2000 lines and 1.5 MiB, a failure of the
    archive never fails the refresh, a show with no archive gets none."""
    expect = ctx.expect
    F = 'https://feeds.example/a'
    A, E = f'{RD}/A/.archive', f'{RD}/A/.episodes'
    m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
    arch = eps_text(*[dict(g=f'g{i}', p=BASE + i, f=f'e{i}.mp3', t=f'Ep {i}', u=f'u{i}') for i in range(50, 0, -1)])
    m.put(A, arch)
    sites = []
    m.curl_site = lambda url, o: (sites.append(url), {'body': feed([item(i) for i in range(60, 0, -1)])})[1]
    r, th = PCN.start(m, ['A'])
    PCN.work(m, th)
    _, rows = lines_of(m.fs[E])
    _, arows = lines_of(m.fs[A])
    gs = [r['g'] for r in arows]
    expect(len(rows) == 20 and rows[0]['g'] == 'g60' and sites == [F], f'a refresh: .episodes holds the newest 20 ({len(rows)}) from one request of the feed')
    expect(len(arows) == 60 and gs == [f'g{i}' for i in range(60, 0, -1)] and len(set(gs)) == 60,
           f'.archive gained the ten items it lacked (g51 to g60), newest first, each once ({len(arows)} lines)')
    expect(arows[0]['u'] == 'https://cdn.example/e60.mp3' and arows[0]['f'] == rows[0]['f'] and arows[-1] == lines_of(arch)[1][-1], 'the new lines are .episodes\' own (the file name a refresh gave), the old lines are as they were')
    expect(f'{A}.tmp' not in m.fs, 'no temp file is left')
    # nothing new: the archive is not written again
    before = m.fs[A]; m.calls = []
    r, th = PCN.start(m, ['A']); PCN.work(m, th)
    expect(m.fs[A] == before and not [c for c in m.calls if c[0] in ('open', 'write') and c[1] == f'{A}.tmp'], 'a refresh that finds nothing new leaves .archive alone (not rewritten)')
    # a new episode arrives: one line, in front
    m.curl_site = lambda url, o: {'body': feed([item(61)] + [item(i) for i in range(60, 0, -1)])}
    r, th = PCN.start(m, ['A']); PCN.work(m, th)
    _, arows = lines_of(m.fs[A])
    expect(len(arows) == 61 and arows[0]['g'] == 'g61' and arows[1]['g'] == 'g60', 'a later refresh adds only the new episode, in front')
    # the cap: 2000 lines, the oldest dropped
    m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
    m.put(A, eps_text(*[dict(g=f'x{i}', p=BASE + 1000 + i, f=f'x{i}.mp3', t=f'X {i}', u=f'u{i}') for i in range(1999, -1, -1)]))
    m.curl_site = lambda url, o: {'body': feed([item(i, day=5000 + i) for i in range(3, 0, -1)])}
    r, th = PCN.start(m, ['A']); PCN.work(m, th)
    _, arows = lines_of(m.fs[A])
    expect(len(arows) == ARCH_MAX and [r['g'] for r in arows[:3]] == ['g3', 'g2', 'g1'] and arows[-1]['g'] == 'x3', f'a full archive of 2000 lines: three new ones in front, the three oldest dropped ({len(arows)} lines, last {arows[-1]["g"]})')
    # the byte cap: lines of about 900 bytes
    m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
    long_url = 'https://cdn.example/' + 'x' * 600 + '/{}.mp3'
    m.put(A, eps_text(*[dict(g=f'w{i}', p=BASE + 1000 + i, f=f'w{i}.mp3', t='T' * 90, u=long_url.format(i), x='d' * 190) for i in range(1700, 0, -1)]))
    size0 = len(m.fs[A])
    m.curl_site = lambda url, o: {'body': feed([item(i, day=5000 + i) for i in range(3, 0, -1)])}
    r, th = PCN.start(m, ['A']); PCN.work(m, th)
    data = m.fs[A]
    _, arows = lines_of(data)
    expect(len(data) <= ARCH_BYTES and arows[0]['g'] == 'g3' and size0 > ARCH_BYTES - 3000, f'the byte cap holds ({len(data)} of {ARCH_BYTES}), the new lines are in front')
    # a failure of the archive is not the refresh's: .episodes is written, the archive is as it was, the state is a success
    for what, setup in (('its temp file cannot be written', lambda mm: mm.fail.add(('write', f'{A}.tmp'))), ('no memory for the merge', lambda mm: setattr(mm, 'calloc_fail_size', 16400))):
        m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
        m.put(A, arch)
        m.curl_site = lambda url, o: {'body': feed([item(i) for i in range(60, 0, -1)])}
        r, th = PCN.start(m, ['A'])
        setup(m)
        PCN.work(m, th)
        _, rows = lines_of(m.fs[E])
        expect(len(rows) == 20 and rows[0]['g'] == 'g60' and m.fs[A] == arch and f'{A}.tmp' not in m.fs and b'checked=' in m.fs[f'{RD}/A/.show'], f'{what}: .episodes and .show are written, .archive is as it was, no temp file')
    # a show with no archive gets none
    m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
    m.curl_site = lambda url, o: {'body': feed([item(i) for i in range(60, 0, -1)])}
    r, th = PCN.start(m, ['A']); PCN.work(m, th)
    expect(A not in m.fs and f'{A}.tmp' not in m.fs, 'a show with no archive gets none from a refresh')
    # Unsubscribe with no file left removes .archive with the rest
    m = PCN.machine(); PCN.sub(m, 'A', F, checked=1)
    m.put(A, arch)
    expect(m.call(PSYMS['pn_unsubscribe_show'], a0=m.cstr(RD), a1=show_addr(m, 'A'), count=1 << 40) == 2 and A not in m.fs and E not in m.fs,
           'Unsubscribe with no file left removes .archive with .episodes and .show')


def select_tests(ctx):
    """Select mode on a list longer than the old 300: the marks, Select All and Delete reach the last row."""
    expect = ctx.expect
    SEL = sibling('pcsel')
    RP, DEEP = PSH.RP, PSH.DEEP

    def card(mm):
        PSH.deep_card(mm)
        mm.put(f'{RP}/{DEEP}/.archive', eps_text(*[dict(g=f'z{i}', p=1000 + (999 - i), f=f'z{i}.mp3', t=f'Z {i}', u=f'https://cdn.example/z{i}.mp3') for i in range(1000)]))
        mm.put(f'{RP}/{DEEP}/z0.mp3', b'audio')      # the oldest episode of 1008: its row is the last
    m = PSH.machine(card=card); PSH.open_show(m)
    n = len(episodes(m, show_addr(m, DEEP), ARCH_MAX))
    expect(n == 1008, f'the list holds the .episodes entries and the 1000 of the archive ({n})')
    SEL.start_select(m)
    m.calls = []
    PCP.click(m, 'btn_selall')
    expect(('widget_set_text_utf8', m.widgets['label_title'], '5 Selected') in m.calls, 'Select All marks the five episodes with a file (three, a .part and the archive\'s oldest)')
    m.confirm_yes = True; m.calls = []
    PCP.click(m, 'pg_del')
    expect(f'{RP}/{DEEP}/z0.mp3' not in m.fs and f'{RP}/{DEEP}/e0.mp3' not in m.fs, 'Delete removes the file of the last row (row 1007) as well as the first')


def download_tests(ctx):
    expect = ctx.expect
    m = PCN.machine(); PCN.sub(m, 'A', 'https://feeds.example/a')
    m.put(f'{RD}/A/.episodes', eps_text(dict(g='g1', p=1000, f='new.mp3', t='New', u='https://cdn.example/new.mp3')))
    m.put(f'{RD}/A/.archive', eps_text(dict(g='g1', p=1000, f='new.mp3', t='New', u='https://cdn.example/new.mp3'), dict(g='g0', p=10, l=5, f='old.mp3', t='Old', u='https://cdn.example/old.mp3')))
    seen = []
    m.curl_site = lambda url, o: (seen.append(url), {'body': b'AUDIO', 'ctype': 'audio/mpeg', 'length': 5})[1]
    r, th = DL.add(m, 'old.mp3', 'A')
    expect(r == 0 and th, 'an episode only the archive lists can be queued')
    PCN.work(m, th) if th[0] == PSYMS['pn_main'] else m.call(th[0], a0=th[1], count=1 << 40)
    expect(seen == ['https://cdn.example/old.mp3'] and m.fs.get(f'{RD}/A/old.mp3') == b'AUDIO', f'its url came from .archive and the file is on the card ({seen})')
    addr = show_addr(m, 'A')
    got = {e['title']: e for e in m.episodes(addr, ARCH_MAX)}
    expect(got['Old']['state'] == 0 and got['Old']['file'] == 'old.mp3', 'the list now has it on the card (PC_LOCAL)')
    m.call(PSYMS['pc_mark'], a0=got['Old']['hash'], a1=1, count=2000000)
    expect(m.state(got['Old']['hash'])[0] == 2, 'a played mark keys on its file as for any episode')


def row_tests(ctx):
    expect = ctx.expect
    tx = lambda m, off, style='label_ps_ctitle': [(t, r) for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == style]
    bottom = lambda m: max(0, m.props[(m.sv, 'virtual_h')] - 400)
    m = PSH.machine(); PSH.open_show(m)
    h = m.props[(m.sv, 'virtual_h')]
    rows = [t for t, _ in tx(m, bottom(m)) if t == 'See All']
    expect(rows == ['See All'] and h == PSH.pod_show.content_height(PCP.hdr(m), 8, more=True), f'a subscribed show with no archive: the row under the last cell ({rows}, content {h})')
    # the tap starts the job; the row reads Loading... while it runs
    feed_xml = feed([item(i) for i in range(40, 0, -1)])
    m.curl_site = lambda url, o: {'body': feed_xml}
    m.thread = None
    y = PCP.hdr(m) + 8 * PCP.CELL + 20
    PCP.tap(m, 150, y, off=bottom(m))
    expect(m.thread and m.thread[0] == PSYMS['pn_armain'] and state(m)[0] == AR['RUNNING'], 'a tap on the row starts the job')
    expect([t for t, _ in tx(m, bottom(m), 'label_ps_cdim') if t == 'Loading…'] and not [t for t, _ in tx(m, bottom(m)) if t == 'See All'], 'the row reads Loading… while it runs')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(state(m)[0] == AR['IDLE'] and f'{PSH.RP}/{PSH.DEEP}/.archive' in m.fs, 'the tick forgets the finished job; .archive is there')
    expect(m.props[(m.sv, 'virtual_h')] > h + 20 * PCP.CELL and not [t for t, _ in tx(m, bottom(m)) if t in ('See All', 'Loading…')], 'the list now holds the archive (a longer list) and the row is gone')
    # not for a show with no feed, a show that has an archive, a preview
    m = PSH.machine(feed=False); PSH.open_show(m)
    expect(not [t for t, _ in tx(m, bottom(m)) if t == 'See All'] and m.props[(m.sv, 'virtual_h')] == PSH.pod_show.content_height(PCP.hdr(m), 8), 'a show of copied files (no feed): no row')
    m = PSH.machine(card=lambda mm: (PSH.deep_card(mm), mm.put(f'{PSH.RP}/{PSH.DEEP}/.archive', eps_text(dict(g='a', p=1, f='a.mp3', t='A', u='u')))))
    PSH.open_show(m)
    expect(not [t for t, _ in tx(m, bottom(m)) if t == 'See All'], 'a show that has an archive: no row')


SE = sibling('pcsearch')


def sleeps(m): return m.slept


def count_addr(m):
    """Where pn.arn is: pn + the offset pn_arch_count builds in its first lui / ori pair (read from the compiled payload; the function adds it to pn)."""
    a = PSYMS['pn_arch_count']
    w0, w1 = m.word(a), m.word(a + 4)
    assert w0 >> 26 == 0x0f and w1 >> 26 == 0x0d, 'pn_arch_count starts lui / ori'
    return PSYMS['pn'] + ((w0 & 0xffff) << 16 | (w1 & 0xffff))


def failed(m, h): return m.call(PSYMS['pn_arch_failed'], a0=h, count=2000)


def attempts(plan, log):
    """A scripted server: plan is a list of answers, one per request (the last repeats)."""
    def site(url, o):
        log.append(dict(o))
        a = plan[min(len(log) - 1, len(plan) - 1)]
        return a(url, o) if callable(a) else a
    return site


def retry_tests(ctx):
    expect = ctx.expect
    F = 'https://feeds.example/a'
    H = PCN.pc_hash('A')
    good = {'body': feed([item(i) for i in (2, 1, 0)])}
    part = lambda n: {'body': feed([item(i) for i in range(n, 0, -1)]).rsplit(b'</channel>', 1)[0], 'partial': True, 'rc': 6, 'chunk': 100}
    # 1. A network error twice, then the answer: one second apart, each attempt starts a fresh file (the half feed of the first is not in the result)
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    st = run_job(m, attempts([part(5), {'rc': 28}, good], log))
    _, rows = lines_of(m.fs[f'{RD}/A/.archive'])
    expect(st == (AR['DONE'], 0) and len(log) == 3 and sleeps(m) == [1, 1] and [r['g'] for r in rows] == ['g2', 'g1', 'g0'] and f'{RD}/A/.archive.tmp' not in m.fs and failed(m, H) == 0,
           f'two failures then the answer: three requests, a second apart, only the last attempt\'s items ({len(log)} requests, waits {sleeps(m)}, {len(rows)} lines)')
    # 2. Three failures: the code of the last, no file, remembered for the show
    for what, plan, code in (('a network error', [{'rc': 6}], PN['NET']), ('a time-out', [{'rc': 28}], PN['NET']), ('HTTP 503', [{'rc': 22, 'code': 503}], PN['HTTP']), ('HTTP 429', [{'rc': 22, 'code': 429}], PN['HTTP'])):
        m = PCN.machine(); PCN.sub(m, 'A', F); log = []
        st = run_job(m, attempts(plan, log))
        expect(st == (AR['FAILED'], code) and len(log) == 3 and sleeps(m) == [1, 1] and f'{RD}/A/.archive' not in m.fs and f'{RD}/A/.archive.tmp' not in m.fs and failed(m, H) == code and failed(m, H + 1) == 0,
               f'{what}: three attempts, two waits, PN code {code}, no files, remembered for that show ({len(log)} requests)')
    # 3. Final failures are not asked again
    for what, plan, code in (('HTTP 404', [{'rc': 22, 'code': 404}], PN['GONE']), ('HTTP 410', [{'rc': 22, 'code': 410}], PN['GONE']), ('HTTP 403', [{'rc': 22, 'code': 403}], PN['HTTP']),
                             ('a page that is not a feed', [{'body': b'<html><body>hi</body></html>'}], PN['NOTFEED']), ('a certificate', [{'rc': 60}], PN['CERT'])):
        m = PCN.machine(); PCN.sub(m, 'A', F); log = []
        st = run_job(m, attempts(plan, log))
        expect(st == (AR['FAILED'], code) and len(log) == 1 and sleeps(m) == [] and failed(m, H) == code, f'{what}: one request, no retry, PN code {code}')
    m = PCN.machine(); PCN.sub(m, 'A', F); m.card_mounted = False
    m.curl_site = lambda u, o: {'body': feed([item(1)])}
    r, th = start(m)
    expect(r == PN['STORAGE'], 'no card: the guard says storage and nothing starts')
    # 4. Stall detection as the downloads have it, on top of the 300 s limit
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    run_job(m, attempts([good], log))
    expect(log[0][19] == 1 and log[0][20] == 60 and log[0][13] == 300, 'a request fails after 60 s under 1 byte a second (PN_DL_STALL) and after 300 s in all')
    # 5. A later success or a new start forgets the failure
    m = PCN.machine(); PCN.sub(m, 'A', F)
    run_job(m, lambda u, o: {'rc': 6}); m.call(PSYMS['pn_arch_reset'], count=2000)
    expect(failed(m, H) == PN['NET'], 'reset keeps the failure for the row')
    expect(run_job(m, good['body']) == (AR['DONE'], 0) and failed(m, H) == 0, 'a success forgets it')
    # 6. The count: items written so far (0 at the start of every attempt)
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    run_job(m, attempts([part(40), part(7)], log))
    expect(m.word(count_addr(m)) == m.call(PSYMS['pn_arch_count'], count=2000) and 5 <= m.call(PSYMS['pn_arch_count'], count=2000) <= 7,
           f'the counter is the last attempt\'s ({m.call(PSYMS["pn_arch_count"], count=2000)}), not a sum')
    m = PCN.machine(); PCN.sub(m, 'A', F)
    run_job(m, feed([item(i) for i in range(30, 0, -1)]))
    expect(m.call(PSYMS['pn_arch_count'], count=2000) == 30, 'a finished job: all 30 items counted')
    # 7. Cancel: while the transfer runs (the worker's own cancel word), between two attempts, at once
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    st = run_job(m, attempts([lambda u, o: dict(part(30), xfer=lambda url, sent, total: SE.cancel(m))], log))
    expect(st == (AR['FAILED'], PN['CANCELLED']) and len(log) == 1 and sleeps(m) == [] and f'{RD}/A/.archive' not in m.fs and f'{RD}/A/.archive.tmp' not in m.fs and failed(m, H) == 0 and not m.call(PSYMS['pn_job_busy'], count=2000),
           'a cancel during the transfer: PN_CANCELLED, no .archive, no temp file, nothing remembered, the slot is free')
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    m.on_sleep = lambda k: SE.cancel(m)
    st = run_job(m, attempts([{'rc': 6}], log))
    expect(st == (AR['FAILED'], PN['CANCELLED']) and len(log) == 1 and f'{RD}/A/.archive.tmp' not in m.fs, 'a cancel during the wait between attempts: no second request')
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    m.curl_site = attempts([good], log)
    r, th = start(m)
    m.call(PSYMS['pn_cancel'], a0=1 << 10, count=2000)   # (PN_KIND_ARCH, one of PN_K_PODCASTS)
    PCN.work(m, th)
    expect(state(m) == (AR['FAILED'], PN['CANCELLED']) and not log and f'{RD}/A/.archive' not in m.fs, 'cancelled before the worker ran: no request, no file')
    m = PCN.machine(); PCN.sub(m, 'A', F); log = []
    st = run_job(m, attempts([lambda u, o: dict(good, xfer=lambda url, sent, total: SE.cancel(m) if sent >= len(good['body']) else None)], log))
    expect(st == (AR['FAILED'], PN['CANCELLED']) and f'{RD}/A/.archive' not in m.fs, 'a cancel that comes with the last byte still leaves no archive')


def page_tests(ctx):
    """The row and the page around the job: the count, the failure that stays, leaving and returning, a cancel, the page closed or in the background."""
    expect = ctx.expect
    tx = lambda m, style='label_ps_ctitle': [t for (t, r), s in zip(*PCP.paint(m, bottom(m))[1:3]) if s == style][-1:]   # (the last text of the style: the row under the cells)
    bottom = lambda m: max(0, m.props[(m.sv, 'virtual_h')] - 400)
    row_y = lambda m: PCP.hdr(m) + 8 * PCP.CELL + 20
    toasted = lambda m, word: word in str(m.calls)
    tick = lambda m, fn='pg_tick': m.call(PSYMS[fn], a0=0, count=40000000)
    dead = lambda u, o: {'rc': 6}
    feed_xml = feed([item(i) for i in range(40, 0, -1)])

    def shown(site):
        m = PSH.machine(); PSH.open_show(m)
        m.curl_site = site
        m.thread = None
        PCP.tap(m, 150, row_y(m), off=bottom(m))
        return m

    # 1. The count: Loading… at first, then Loading… and the items so far, refreshed by the page's tick; a tap while it loads does nothing
    m = shown(lambda u, o: {'body': feed_xml})
    th = m.thread
    expect(tx(m, 'label_ps_cdim') == ['Loading…'], f'the row reads Loading… before the first item ({tx(m, "label_ps_cdim")})')
    m.setword(count_addr(m), 340)
    tick(m)
    expect(tx(m, 'label_ps_cdim') == ['Loading… 340'], f'with 340 items written: Loading… 340 ({tx(m, "label_ps_cdim")})')
    m.thread = None
    PCP.tap(m, 150, row_y(m), off=bottom(m))
    expect(m.thread is None and state(m)[0] == AR['RUNNING'], 'a tap on the row while it loads does nothing')
    PCN.work(m, th)
    tick(m)
    expect(state(m)[0] == AR['IDLE'] and tx(m) not in (['See All'], ['Loading…']), 'the job ended: the row is gone with the long list')

    # 2. A failure: toast on that show, the reason and the hint stay on the row, leaving and returning keeps them, a tap retries
    m = shown(dead)
    PCN.work(m, m.thread)
    tick(m)
    expect(toasted(m, "Can't connect") and state(m)[0] == AR['IDLE'] and tx(m) == ["Can't connect \u00b7 Tap to Retry"], f'a failure: the toast, then the reason and the hint on the row ({tx(m)})')
    PCP.click(m, 'btn_return')
    PSH.open_show(m)
    expect(tx(m) == ["Can't connect \u00b7 Tap to Retry"], 'leaving the show and coming back: the row still says why')
    m.curl_site = lambda u, o: {'body': feed_xml}; m.thread = None
    PCP.tap(m, 150, row_y(m), off=bottom(m))
    expect(m.thread and m.thread[0] == PSYMS['pn_armain'] and tx(m, 'label_ps_cdim') == ['Loading…'], 'a tap on it retries: Loading… again')
    PCN.work(m, m.thread)
    tick(m)
    expect(f'{PSH.RP}/{PSH.DEEP}/.archive' in m.fs and 'Retry' not in str(tx(m)), 'the retry succeeded: the archive, no hint')

    # 3. The job ends while the user is on another page of Podcasts: no toast, the hint is on the row when the show is opened again
    m = shown(dead)
    th = m.thread
    PCP.click(m, 'btn_return')
    PCN.work(m, th)
    tick(m)
    expect(not toasted(m, "Can't connect") and state(m)[0] == AR['IDLE'], 'a failure while the Shows level is open: no toast, the finished job is forgotten')
    PSH.open_show(m)
    expect(tx(m) == ["Can't connect \u00b7 Tap to Retry"], 'opening the show: the reason and the hint')
    # (the job that runs on while the user is elsewhere: coming back shows the live count)
    m = shown(lambda u, o: {'body': feed_xml})
    PCP.click(m, 'btn_return'); PSH.open_show(m); m.setword(count_addr(m), 12); tick(m)
    expect(state(m)[0] == AR['RUNNING'] and tx(m, 'label_ps_cdim') == ['Loading… 12'], 'leaving the show while the job runs and coming back: the job went on, the row shows the count')

    # 4. Another job takes the worker (the page's way: a job that runs is cancelled): the archive job stops, leaves nothing, shows no toast; the downloads that ran beside it go on
    m = shown(lambda u, o: {'body': feed_xml})
    th = m.thread
    r, dth = DL.add(m, 'e5.mp3', PSH.DEEP)
    expect(r == 0 and dth and dth[0] == PSYMS['pn_dmain'] and m.call(PSYMS['pn_dl_running'], count=2000) == 1 and m.call(PSYMS['pn_job_busy'], count=2000) == 1, 'a download queued while the job runs starts its own thread at once')
    m.call(PSYMS['pg_srch_leave'], count=2000000)
    m.curl_site = lambda u, o: dict({'body': feed_xml, 'chunk': 200}, xfer=lambda url, sent, total: None)
    PCN.work(m, th)
    m.calls = []; m.thread = None
    tick(m)
    expect(state(m)[0] == AR['IDLE'] and not toasted(m, 'connect') and f'{PSH.RP}/{PSH.DEEP}/.archive' not in m.fs and f'{PSH.RP}/{PSH.DEEP}/.archive.tmp' not in m.fs
           and m.thread is None and m.call(PSYMS['pn_dl_running'], count=2000) == 1 and tx(m) == ['See All'],
           'cancelled by another job: no archive, no temp file, no toast, the row as before; the tick starts no second download thread, the first one still runs')
    m.curl_site = DL.server(DL.DATA)
    DL.work(m, dth)
    expect(m.call(PSYMS['pn_dl_running'], count=2000) == 0 and m.call(PSYMS['pn_dl_count'], count=2000) == 0 and m.fs.get(f'{PSH.RP}/{PSH.DEEP}/e5.mp3') == DL.DATA, 'and the download then finishes: the episode is a file')

    # 5. The device is kept awake while the job runs; the end is seen by that timer when the page's own is stopped (another page in front)
    m = shown(lambda u, o: {'body': feed_xml})
    th = m.thread
    expect(('timer_add', PSYMS['pg_awake_tick'], 1000) in m.calls or any(c[0] == 'timer_add' and c[1] == PSYMS['pg_awake_tick'] for c in m.calls), 'the job armed the downloads\' timer')
    m.calls = []
    r = tick(m, 'pg_awake_tick')
    expect(r == O['RET_REPEAT'] and [c for c in m.calls if c[0] == 'reset_poweroptions_timer'] == [('reset_poweroptions_timer', 1, 1, 0)], 'while the job runs the timer calls reset_poweroptions_timer(1, 1, 0) and goes on, as for a download')
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn, a0=c, a1=0, count=4000000)
    r, dth = DL.add(m, 'e5.mp3', PSH.DEEP)
    PCN.work(m, th)
    m.thread = None
    tick(m, 'pg_awake_tick')
    expect(state(m)[0] == AR['IDLE'] and m.thread is None and m.call(PSYMS['pn_dl_running'], count=2000) == 1, 'the page in the background: the downloads\' timer forgets the finished job; the download thread that ran beside it still runs, none is started')

    # 6. The page is closed while the job runs: the job is cancelled, a timer with no page forgets it once the worker is free; the downloads run beside it
    m = shown(lambda u, o: {'body': feed_xml})
    th = m.thread
    r, dth = DL.add(m, 'e5.mp3', PSH.DEEP)
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, a1=0, count=20000000)
    expect(any(c[0] == 'timer_add' and c[1] == PSYMS['pg_resume_tick'] for c in m.calls), 'closing the page: a resume timer is armed')
    m.thread = None
    r = tick(m, 'pg_resume_tick')
    expect(r == O['RET_REPEAT'] and m.thread is None, 'the worker is still busy: the resume timer waits')
    PCN.work(m, th)
    r = tick(m, 'pg_resume_tick')
    expect(r == 0 and state(m)[0] == AR['IDLE'] and f'{PSH.RP}/{PSH.DEEP}/.archive' not in m.fs and m.thread is None and m.call(PSYMS['pn_dl_running'], count=2000) == 1 and dth and dth[0] == PSYMS['pn_dmain'],
           'the job ended cancelled: the timer ends, no archive, no download thread started (the one beside the job still runs)')


def spin_tests(ctx):
    """The See All row's spinner (patch/podcasts.c pg_spin_*): the Wi-Fi page's 14 px frame left of the dim text while the job runs, turned by its own 250 ms timer, gone (and the timer with it) when the row is idle,
    failed, ended, left, or the page is closed."""
    expect = ctx.expect
    bottom = lambda m: max(0, m.props[(m.sv, 'virtual_h')] - 400)
    row_y = lambda m: PCP.hdr(m) + 8 * PCP.CELL + 20
    tick = lambda m, fn='pg_tick': m.call(PSYMS[fn], a0=0, count=40000000)
    dead = lambda u, o: {'rc': 6}
    feed_xml = feed([item(i) for i in range(40, 0, -1)])
    spin = lambda m: [b for b in PCP.paint(m, bottom(m))[0] if m.bitmaps[b[0]][1:] == (14, 14)]
    adds = lambda m: [t for t in m.timers if t[0] == PSYMS['pg_spin_tick']]   # (every timer_add of the machine, in order)
    dim = lambda m: [r for (t, r), st in zip(*PCP.paint(m, bottom(m))[1:3]) if st == 'label_ps_cdim']
    RR = O['RET_REPEAT']

    def shown(site, tap=True):
        m = PSH.machine()
        for i in range(8): m.images[f'wf_spin{i}'] = (14, 14, bytes((0x55, 0x55, 0x55, 255)) * 196)   # (the Wi-Fi page's frames as cc_decode flattens them over black)
        PSH.open_show(m)
        m.curl_site = site
        m.thread = None
        if tap: PCP.tap(m, 150, row_y(m), off=bottom(m))
        return m

    # 1. Idle: no spinner, no timer; the job starts: one spinner at the text's left edge, the text after it, one 250 ms timer
    m = shown(lambda u, o: {'body': feed_xml}, tap=False)
    expect(spin(m) == [] and not adds(m) and dim(m) == [], 'the idle row ("See All"): no spinner, no timer')
    PCP.tap(m, 150, row_y(m), off=bottom(m))
    th = m.thread
    sp = spin(m)
    expect(len(sp) == 1 and sp[0][2][0] == O['PS_CELL_X'] and sp[0][2][2:] == (14, 14) and dim(m)[0][0] == O['PS_CELL_X'] + 14 + O['PS_SPIN_GAP'],
           f'the job runs: one 14 px spinner at x {O["PS_CELL_X"]}, the dim text after it ({[b[2] for b in sp]}, {dim(m)})')
    expect(len(adds(m)) == 1 and (PSYMS['pg_spin_tick'], O['PS_SPIN_MS']) in m.timers and O['PS_SPIN_MS'] == 250, 'one timer of 250 ms')
    # 2. The frame advances with the timer (eight frames, then round)
    seen = [sp[0][0]]
    for _ in range(8):
        expect(tick(m, 'pg_spin_tick') == RR, 'the timer goes on while the row is busy')
        seen.append(spin(m)[0][0])
    expect(len(set(seen[:8])) == 8 and seen[8] == seen[0] and seen[1] != seen[0], f'each tick shows the next frame, eight of them ({len(set(seen[:8]))} different)')
    expect(len(adds(m)) == 1, 'the page tick does not add a second timer while one runs')
    tick(m)
    expect(len(adds(m)) == 1, 'the page tick does not add a second timer')
    # 3. The job ends: no spinner, the timer ends itself (RET_OK) and its handle is forgotten, so the next job arms another
    PCN.work(m, th)
    tick(m)
    expect(state(m)[0] == AR['IDLE'] and tick(m, 'pg_spin_tick') != RR and spin(m) == [], 'the job ended: the timer ends and no spinner is drawn')
    # 4. A failure: no spinner, the reason on the row at the text's own place
    m = shown(dead)
    expect(len(spin(m)) == 1, 'a second show: the spinner while it loads')
    PCN.work(m, m.thread)
    tick(m)
    expect(spin(m) == [] and dim(m) == [] and tick(m, 'pg_spin_tick') != RR, 'a failure: no spinner, the timer ended')
    expect(any(r[0] == O['PS_CELL_X'] for (t, r), st in zip(*PCP.paint(m, bottom(m))[1:3]) if st == 'label_ps_ctitle' and t.endswith('Tap to Retry')), 'the failure text starts at the cell edge, not after a spinner')
    # 5. Leaving the show ends the timer; coming back while the job runs arms it again
    m = shown(lambda u, o: {'body': feed_xml})
    PCP.click(m, 'btn_return')
    expect(tick(m, 'pg_spin_tick') != RR, 'the Shows level: the timer ends')
    PSH.open_show(m)
    tick(m)
    expect(len(adds(m)) == 2 and len(spin(m)) == 1, 'back on the show with the job still running: the spinner and a new timer')
    # 6. The page closes: the spinner timer is removed (one timer_remove more than for a page whose spinner timer has ended)
    def removes(m):
        m.calls = []
        fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
        m.call(fn, a0=c, a1=0, count=40000000)
        return len([c for c in m.calls if c[0] == 'timer_remove'])
    live = removes(shown(lambda u, o: {'body': feed_xml}))
    m = shown(lambda u, o: {'body': feed_xml})
    PCP.click(m, 'btn_return')
    tick(m, 'pg_spin_tick')
    expect(live == removes(m) + 1, 'closing the page removes the spinner timer')


SECTIONS = [job_tests, retry_tests, model_tests, recent_tests, keep_tests, refresh_tests, download_tests, row_tests, page_tests, spin_tests, select_tests, markall_tests]
