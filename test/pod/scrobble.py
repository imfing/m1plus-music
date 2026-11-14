"""Offline scrobbling (patch/scrobble.c, docs/modules/scrobble.md): the seconds heard from the player's position (steps, seeks, pauses, a page left and come
back to, repeat one), the listen rule (half or SC_MAX_S of a track longer than SC_MIN_S, once per play), the log line and header, what is not logged (podcasts,
no artist, a short track, an unset clock, the kill switch, no card), the tag reader's start (stock's get_id3info for real: the file's tags, the time before
the first look, the track it replaces extrapolated to its end) and its cost on the boot path; the automatic upload (the Auto Upload switch, what the poll pays
for it while it is off or nothing waits, the listens counted, the wait, the look once a minute, every condition, every outcome, whose job a poll is). The compiled
payload runs under Unicorn with the stock calls mocked (the Podcasts test's machines; the upload's thread routine is run by the test, libcurl is scrobup's scripted
service)."""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

podcasts = sibling('podcasts')
LOG = '/mnt/mmc/.scrobbler.log'
HEADER = '#AUDIOSCROBBLER/1.1\n#TZ/UTC\n#CLIENT/M1+ Music\n'
MIN_S, MAX_S, POLL_MS, SLACK_S = O['SC_MIN_S'], O['SC_MAX_S'], O['SC_POLL_MS'], O['SC_SLACK_S']
WALL = 1800000000


SETTING = '/mnt/data/m1plus/scrobbling'


def machine(cls=None, on=True):
    """A machine with the setting on (and read, as the first poll would) unless on is False."""
    m = (cls or podcasts.PM)()
    m.wall, m.clock = WALL, 1000
    if on:
        m.fs[SETTING] = b'1\n'
        m.call(PSYMS['scrobble_setting'], count=200000); m.calls = []
    return m


def song(m, path='/mnt/mmc/Music/Kind of Blue/02 Freddie.flac', artist='Miles Davis', album='Kind of Blue', title='Freddie Freeloader', track=2, cue=0):
    r = m.record(album=album, artist=artist, path=path, title=title, name=path.rsplit('/', 1)[1])
    m.setword(r + O['REC_TRACK'], track); m.setword(r + O['REC_CUE_START'], cue)
    m.play([r], 0)
    return r


def tick(m, dt):
    """dt ms pass: the ms clock and the wall clock (whole seconds) together."""
    m.clock += dt
    m.ms = getattr(m, 'ms', 0) + dt
    m.wall += m.ms // 1000; m.ms %= 1000


def note(m, rec, pos=None, ln=None, dt=0):
    """One look dt ms after the last, the player at pos of ln seconds (unchanged when None)."""
    tick(m, dt)
    if pos is not None: m.pt = (pos, ln if ln is not None else m.pt[1], 1)
    m.call(PSYMS['scrobble_note'], a0=rec, count=2000000)


def play(m, rec, start, end, ln, step=1):
    """Plays from start to end seconds, a look every `step` seconds."""
    for p in range(start, end + 1, step): note(m, rec, p, ln, step * 1000)


def lines(m):
    return [l for l in m.fs.get(LOG, b'').decode('utf-8').split('\n') if l and not l.startswith('#')]


def line(artist='Miles Davis', album='Kind of Blue', title='Freddie Freeloader', track='2', ln=300, stamp=0):
    return f'{artist}\t{album}\t{title}\t{track}\t{ln}\tL\t{stamp}\t'


def rule_tests(ctx):
    """The listen rule, the line, once per play, a play again."""
    expect = ctx.expect
    expect((MIN_S, MAX_S, POLL_MS, SLACK_S) == (30, 240, 500, 2), 'q2-pod\'s rule: over 30 s long, half or 4 minutes heard; the player asked every 500 ms at most, a step counts within 2 s of the wall time')
    m = machine(); r = song(m)
    note(m, r, 0, 300)
    play(m, r, 1, 149, 300)
    expect(LOG not in m.fs, '149 s of 300: no listen yet')
    note(m, r, 150, 300, 1000)
    expect(m.fs.get(LOG, b'').decode() == HEADER + line(stamp=WALL) + '\n',
           f'at half the length: the header (the file was not there), then one line, the start time the play\'s second 0 ({m.fs.get(LOG)!r})')
    play(m, r, 151, 300, 300, 5)
    expect(len(lines(m)) == 1, 'once per play: the rest of the track adds nothing')
    note(m, r, 0, 300, 1000); again = m.wall; play(m, r, 1, 151, 300, 2)
    expect(len(lines(m)) == 2 and lines(m)[1] == line(stamp=again) and m.fs[LOG].decode().count('#AUDIOSCROBBLER') == 1, 'back to second 0 from past 30 s (repeat one): a new play, logged again; the header once')
    # 4 minutes of a long track
    m = machine(); r = song(m); note(m, r, 0, 1000)
    play(m, r, 1, MAX_S - 1, 1000, 1)
    expect(not lines(m), '239 s of 1000: none')
    note(m, r, MAX_S, 1000, 1000)
    expect(lines(m) == [line(ln=1000, stamp=WALL)], 'at 240 s heard: a listen (under half the length)')
    # a short track never
    m = machine(); r = song(m); note(m, r, 0, MIN_S); play(m, r, 1, MIN_S, MIN_S)
    expect(not lines(m), 'a track of 30 s, heard to its end: never a listen')
    m = machine(); r = song(m); note(m, r, 0, MIN_S + 1); play(m, r, 1, 16, MIN_S + 1)
    expect(len(lines(m)) == 1, 'a track of 31 s: half of it is a listen')
    play(m, r, 17, MIN_S, MIN_S + 1); note(m, r, 0, MIN_S + 1, 1000); play(m, r, 1, 16, MIN_S + 1)
    expect(len(lines(m)) == 2, 'repeat one of a 31 s track last seen at 30 s: back to second 0 is a new play, logged again')


def step_tests(ctx):
    """What counts as heard: steps within the wall time, not seeks or pauses; any period."""
    expect = ctx.expect
    m = machine(); r = song(m); note(m, r, 10, 300)
    note(m, r, 200, 300, 1000)
    expect(not lines(m), 'a seek forward (190 s in one second): nothing heard')
    play(m, r, 201, 251, 300)
    expect(not lines(m), 'then 51 s heard of the 150 needed')
    note(m, r, 251, 300, 600000)
    expect(not lines(m), 'ten minutes paused: nothing')
    note(m, r, 350, 300, 100000)
    expect(lines(m) == [line(stamp=WALL - 10)], 'a page left for 100 s and the position 99 s on: heard (the step is within the wall time); 51 + 99; the start is the first look less its position, ten minutes of pause do not move it')
    m = machine(); r = song(m); note(m, r, 0, 300); play(m, r, 1, 100, 300); note(m, r, 100, 300, 3600000); play(m, r, 101, 150, 300)
    expect(lines(m) == [line(stamp=WALL)], f'an hour paused at 100 s: the start stays the play\'s second 0 ({lines(m)})')
    m = machine(); r = song(m); note(m, r, 0, 300)
    for p in range(10, 160, 10): note(m, r, p, 300, 10000)
    expect(len(lines(m)) == 1, 'a look every 10 s counts the same')
    m = machine(); r = song(m); note(m, r, 100, 300); note(m, r, 40, 300, 1000); play(m, r, 41, 189, 300)
    expect(not lines(m), 'a seek back: nothing heard, and no new play unless it lands at the start (149 s heard)')
    note(m, r, 190, 300, 1000)
    expect(len(lines(m)) == 1, 'the 150th second: the listen')
    # the poll period
    m = machine(); r = song(m); note(m, r, 0, 300); m.calls = []
    note(m, r, 0, 300, POLL_MS - 1)
    expect('get_playtimeandlength' not in m.names(), 'a second look within 500 ms does not ask the player (the iPod page ticks faster; a main-loop poll would too)')
    note(m, r, 1, 300, 1)
    expect('get_playtimeandlength' in m.names(), 'at 500 ms it does')
    # the player without a length
    m = machine(); r = song(m); m.pt = (0, 0, 1); note(m, r); m.pt = (5, 300, 0); note(m, r, dt=1000)
    expect(LOG not in m.fs, 'no length or a failed call: nothing')


def skip_tests(ctx):
    """What is never logged, and what writes nothing."""
    expect = ctx.expect
    def heard(m, r):
        note(m, r, 0, 300); play(m, r, 1, 160, 300)
    m = machine(); r = song(m, path='/mnt/mmc/Podcasts/Show/ep.mp3'); m.calls = []; heard(m, r)
    expect(LOG not in m.fs and 'get_playtimeandlength' not in m.names(), 'a podcast: not scrobbled, the player not asked')
    m = machine(); r = song(m); note(m, r, 0, 300); play(m, r, 1, 100, 300)
    p = song(m, path='/mnt/mmc/Podcasts/Show/ep.mp3'); note(m, p, 0, 300, 100000)
    expect(lines(m) == [line(stamp=WALL)], 'music at 100 of 300 s, then a podcast 100 s later: the music track is over, extrapolated to 200 s heard')
    for a in ('', 'Unknown'):
        m = machine(); r = song(m, artist=a); heard(m, r)
        expect(LOG not in m.fs, f'artist {a!r}: not logged (scrobblers refuse it)')
    m = machine(); m.wall = 1000000; r = song(m); heard(m, r)
    expect(LOG not in m.fs, 'a clock before 2020 (never set): not logged')
    m.wall = WALL; note(m, r, 161, 300, 1000)
    expect(lines(m) == [line(stamp=WALL - 160)], f'the clock set later (Auto Time): logged at the next look, the start the wall clock less the time since second 0 ({lines(m)})')
    for what, undo in (('the kill switch', lambda m: m.present.discard('/mnt/mmc/m1plus-off')), ('no card', lambda m: setattr(m, 'card_mounted', True)),
                       ('the log cannot be opened', lambda m: m.fail.discard(('open', LOG))), ('nothing written', lambda m: m.fail.discard(('write', LOG)))):
        m = machine()
        if what == 'the kill switch': m.present.add('/mnt/mmc/m1plus-off')
        if what == 'no card': m.card_mounted = False
        if what == 'the log cannot be opened': m.fail.add(('open', LOG))
        if what == 'nothing written': m.fail.add(('write', LOG))
        r = song(m); heard(m, r)
        expect(not lines(m), f'{what}: nothing written, nothing crashes')
        undo(m); note(m, r, 161, 300, 1000); note(m, r, 162, 300, 1000)
        expect(lines(m) == [line(stamp=WALL)], f'{what}, then fixed: the listen is written at the next look, once ({lines(m)})')
    # the text
    m = machine(); r = song(m, artist='A\tB', album='X\nY', title='', track=0, path='/mnt/mmc/Music/x/Some.Song.flac'); heard(m, r)
    expect(lines(m) == [line('A B', 'X Y', 'Some.Song', '', stamp=WALL)], f'tabs and newlines become spaces; no title: the file name less its extension; no track number: empty ({lines(m)})')
    m = machine(); long = 'é' * 300; r = song(m, artist=long, album='a', title='t'); heard(m, r)
    a = lines(m)[0].split('\t')[0]
    expect(a == 'é' * 127, f'a field cut under 256 bytes before a UTF-8 continuation byte ({len(a.encode())} bytes)')
    # CUE tracks of one image are different tracks
    m = machine(); r1 = song(m, cue=0); note(m, r1, 0, 300); play(m, r1, 1, 100, 300)
    r2 = song(m, cue=300, title='Next'); note(m, r2, 0, 300, 1000); play(m, r2, 1, 150, 300)
    expect(lines(m) == [line(title='Next', stamp=WALL + 101)], 'a CUE image\'s next track (same path, another start) is a track of its own: the one before (101 s of 300) is over and not a listen')


def hook_tests(ctx):
    """The tag reader's start: stock's get_id3info for real over the site."""
    expect = ctx.expect
    pa, pb = '/mnt/mmc/Music/a/1.flac', '/mnt/mmc/Music/a/2.flac'
    m = machine(podcasts.ID3)
    ra = song(m, path=pa, artist='Record Artist', album='Rec', title='Rec Title', track=7)
    m.parse(pa, record=ra, title='Tag Title', artist='Tag Artist', album='Tag Album')
    expect(LOG not in m.fs and 'get_playtimeandlength' not in m.names(), 'a start: nothing written, the player not asked')
    note(m, ra, 100, 200, 100000)
    expect(lines(m) == [line('Tag Artist', 'Tag Album', 'Tag Title', '7', 200, WALL)],
           f'first seen 100 s after its start at 100 s: heard from the start; the file\'s tags (stock\'s parse), the record\'s track number ({lines(m)})')
    # the track it replaces: from its last look to its end
    m = machine(podcasts.ID3)
    ra = song(m, path=pa, track=1); m.parse(pa, record=ra, title='A', artist='Art', album='Alb')
    note(m, ra, 40, 200, 40000)
    rb = song(m, path=pb); tick(m, 300000); m.parse(pb, record=rb, title='B', artist='Art', album='Alb')
    expect(lines(m) == [line('Art', 'Alb', 'A', '1', 200, WALL)], f'the next start 300 s later: the first track heard from 40 s to its end (200 s), logged ({lines(m)})')
    m = machine(podcasts.ID3)
    ra = song(m, path=pa); m.parse(pa, record=ra, title='A', artist='Art', album='Alb'); note(m, ra, 10, 200, 10000)
    rb = song(m, path=pb); tick(m, 50000); m.parse(pb, record=rb, title='B', artist='Art', album='Alb')
    expect(not lines(m), 'skipped after 60 s of 200: not a listen')
    m = machine(podcasts.ID3)
    ra = song(m, path=pa); m.parse(pa, record=ra, title='A', artist='Art', album='Alb')
    rb = song(m, path=pb); tick(m, 300000); m.parse(pb, record=rb, title='B', artist='Art', album='Alb')
    expect(LOG not in m.fs, 'a track no timer saw has no length: not logged')
    # Memory Playback: a start that resumes in the middle
    m = machine(podcasts.ID3)
    ra = song(m, path=pa); m.parse(pa, record=ra, title='A', artist='Art', album='Alb')
    note(m, ra, 120, 200, 1000); play(m, ra, 121, 199, 200)
    expect(not lines(m), 'resumed at 120 s: the jump is no time heard (79 s after it)')
    # a tick with stock's struct for the track: its tags; a record of another track: the record's
    m = machine(podcasts.ID3)
    ra = song(m, path=pa, artist='Rec Artist'); m.parse(pa, record=ra, title='T', artist='Tag Artist', album='Alb')
    m.call(PSYMS['scrobble_started'], a0=pod.DATA['PLAYSONG_ID3INFO'][0], a1=m.cstr('/mnt/mmc/x.flac'), count=200000)   # another track started meanwhile
    note(m, ra, 0, 300, 1000); play(m, ra, 1, 150, 300)
    expect(lines(m)[0].startswith('Tag Artist\t'), 'a timer\'s first look takes stock\'s parsed tags when the struct is that track\'s')
    m = machine(podcasts.ID3); rb = song(m, path=pb, artist='Rec Artist', album='Rec Album', title='Rec Title'); note(m, rb, 0, 300); play(m, rb, 1, 150, 300)
    expect(lines(m)[0].startswith('Rec Artist\tRec Album\tRec Title\t'), 'else the record\'s')
    # the boot path: a copy, a hash and three tags, no player call
    mp = '/mnt/mmc/Music/Boards of Canada/Music Has the Right to Children/03 - Roygbiv.flac'
    tags = dict(title='Roygbiv (Remastered 2013)', artist='Boards of Canada', album='Music Has the Right to Children')
    a = machine(podcasts.ID3).count(); a.parse(mp, **tags)
    b = machine(lambda: podcasts.ID3(stock=True)).count(); b.parse(mp, **tags)
    expect(a.icount - b.icount < 4000 and LOG not in a.fs and a.names() == b.names(),
           f'a music start at boot costs {a.icount - b.icount} instructions more than stock (the path copy, the key, three tags), makes the stock calls and no other, and writes nothing')


def setting_tests(ctx):
    """Settings > Library > Scrobbling > Scrobbling: off by default; while off nothing is asked or written; the switch saved atomically; read once."""
    expect = ctx.expect
    sw = pod_pages.SCROBBLING_PAGE.rows
    expect([(r.label, r.action) for r in sw if r.action == pod_pages.ACT_SCROBBLE] == [('Scrobbling', pod_pages.ACT_SCROBBLE)] and pod_pages.ACT_SCROBBLE in pod_pages.SWITCH_ACTIONS,
           'a switch row on Settings > Library > Scrobbling')
    m = machine(on=False); r = song(m)
    expect(m.call(PSYMS['scrobble_setting'], count=200000) == 0, 'no setting file: off')
    m.calls = []; note(m, r, 0, 300); play(m, r, 1, 200, 300, 10)
    expect(LOG not in m.fs and 'get_playtimeandlength' not in m.names(), 'off: the poll asks the player nothing and nothing is logged')
    expect(m.call(PSYMS['scrobble_toggle'], count=3000000) == 1 and m.fs.get(SETTING) == b'1\n' and ('rename', SETTING + '.tmp', SETTING) in m.calls,
           'the switch: on, saved atomically as "1"')
    note(m, r, 200, 300, 1000); play(m, r, 201, 351, 300)
    expect(len(lines(m)) == 1, 'on: from the first look after it, a listen')
    expect(m.call(PSYMS['scrobble_toggle'], count=3000000) == 0 and m.fs.get(SETTING) == b'0\n' and m.call(PSYMS['scrobble_setting'], count=200000) == 0, 'again: off, saved as "0"')
    for data in (b'0\n', b'', b'x', b'2\n', b'1x', b'11'):
        m = machine(on=False); m.fs[SETTING] = data
        expect(m.call(PSYMS['scrobble_setting'], count=200000) == 0, f'{data!r}: off (only "1" or "1\\n" is on, set_read)')
    m = machine(on=False); m.fail.add(('write', SETTING + '.tmp'))
    t, s = m.call(PSYMS['scrobble_toggle'], count=3000000), m.call(PSYMS['scrobble_setting'], count=200000)
    expect(t == 0xffffffff and s == 0, f'a failed save: -1, still off ({t}, {s})')
    m = machine(); r = song(m); note(m, r, 0, 300); m.calls = []; play(m, r, 1, 20, 300)
    expect(not [c for c in m.calls if c[0] == 'open' and c[1] == SETTING], 'the file is read once, not by every poll')
    # the hook before any poll read the setting (boot): nothing at all
    m = machine(podcasts.ID3, on=False); m.fs[SETTING] = b'1\n'; ra = song(m)
    m.parse('/mnt/mmc/Music/a/1.flac', record=ra, title='A', artist='Art', album='Alb')
    expect(not [c for c in m.calls if c[0] == 'open' and c[1] == SETTING], 'the tag reader\'s hook never reads the file (it runs at boot): it waits for a poll')


# ---- the automatic upload (patch/scrobble.c sa_*, docs/modules/scrobble.md "Automatic upload") ----

SU = sibling('scrobup')
AUTO_FILE = '/mnt/data/m1plus/scrobble-auto'
KILL = '/mnt/mmc/m1plus-off'
EVAL, WAIT, RETRY = O['SA_EVAL'], O['SA_WAIT'], O['SA_RETRY']
SAU = {n: 4 * i for i, n in enumerate(('set', 'job', 'stop', 'fail', 'pending', 'took'))}   # patch/scrobble.c sau
STEP = 10        # seconds between two looks of a waiting test (a page's timer looks every second at most; the period does not matter)
LOUD = ('toast', 'timer_add', 'reset_poweroptions_timer', 'confirm', 'window_open')   # what an automatic upload never does


def auto_machine(auto=True, token=True, answers=None, old=(), on=True, cls=None):
    """A machine with Scrobbling on (unless on is False), Auto Upload on (unless auto is False), an account (unless token is False), the listens old (scrobup's line(i)) in the
    card's log from before this boot, and scrobup's scripted service. m.log keeps every mocked call, m.job the thread of the last upload that started."""
    m = machine(cls, on)
    if auto: m.fs[AUTO_FILE] = b'1\n'
    if token: m.fs[SU.INI] = SU.ini(name='rob').encode()
    if old: m.fs[LOG] = (HEADER + ''.join(SU.line(i) for i in old)).encode()
    m.site = m.curl_site = SU.Site(m, answers)
    m.log, m.job, m.thread = [], None, None
    return m


def look(m, rec, pos=None, ln=None, dt=0):
    """One look (scrobble_note) dt ms after the last; its calls go to m.log, a thread it started to m.job."""
    tick(m, dt)
    if pos is not None: m.pt = (pos, ln if ln is not None else m.pt[1], 1)
    m.thread = None
    m.call(PSYMS['scrobble_note'], a0=rec, count=1 << 28); m.log += m.calls
    if m.thread: m.job = m.thread


def hear(m, k=0):
    """A track heard to half its length: one listen is logged (151 s pass). The record, which goes on playing."""
    r = song(m, path=f'/mnt/mmc/Music/a/{k}.flac', title=f'T{k}')
    look(m, r, 0, 300, 1000)
    for p in range(10, 151, 10): look(m, r, p, 300, 10000)
    return r


def wait(m, r, s, step=STEP):
    """s seconds pass, the track paused, a look every `step` seconds."""
    for _ in range(s // step): look(m, r, dt=step * 1000)


def until_job(m, r, limit, step=STEP):
    """Looks every `step` seconds until an upload's thread starts: the seconds that took, None when none started within limit."""
    m.job = None
    for t in range(step, limit + 1, step):
        look(m, r, dt=step * 1000)
        if m.job: return t
    return None


def finish(m, r):
    """The upload's thread runs to its end, and the next look (a second later) collects its result."""
    SU.call(m, m.job[0], a0=m.job[1], count=1 << 40); m.job = None
    look(m, r, dt=1000)


def sau(m, n): return m.word(PSYMS['sau'] + SAU[n])
def lnames(m): return [c[0] for c in m.log]
def threads(m): return lnames(m).count('pthread_create')
def opens(m, path): return len([c for c in m.log if c[0] == 'open' and c[1] == path])
def quiet(m): return not [c for c in m.log if c[0] in LOUD or c[0].startswith('widget_')]
def auto_toggle(m): return SU.s32(SU.call(m, PSYMS['scrobble_auto_toggle'], count=3000000))
def auto_setting(m): return SU.call(m, PSYMS['scrobble_auto_setting'], count=200000)


def auto_setting_tests(ctx):
    """Settings > Library > Scrobbling > Auto Upload: off by default, saved atomically, read once, a flip seen by the next look."""
    expect = ctx.expect
    P = pod_pages
    expect((EVAL, WAIT, RETRY) == (60, 600, 1800), 'a look at the conditions once a minute, the first waiting listen ten minutes old, half an hour after a failure')
    expect([(r.label, r.action, P.row_kind(r)) for r in P.SCROBBLING_PAGE.rows if r.action == P.ACT_LBAUTO] == [('Auto Upload', P.ACT_LBAUTO, 'switch')] and P.ACT_LBAUTO in P.SWITCH_ACTIONS, 'a switch row on the Scrobbling page')
    m = auto_machine(auto=False)
    expect(auto_setting(m) == 0, 'no setting file: off')
    expect(auto_toggle(m) == 1 and m.fs.get(AUTO_FILE) == b'1\n' and ('rename', AUTO_FILE + '.tmp', AUTO_FILE) in m.log and auto_setting(m) == 1, 'the switch: on, saved atomically as "1"')
    expect(auto_toggle(m) == 0 and m.fs.get(AUTO_FILE) == b'0\n' and auto_setting(m) == 0, 'again: off, saved as "0"')
    for data in (b'0\n', b'', b'x', b'2\n', b'1x', b'11'):
        m = auto_machine(auto=False); m.fs[AUTO_FILE] = data
        expect(auto_setting(m) == 0, f'{data!r}: off (only "1" or "1\\n" is on)')
    m = auto_machine(auto=False); m.fail.add(('write', AUTO_FILE + '.tmp'))
    t, s = auto_toggle(m), auto_setting(m)
    expect(t == -1 and s == 0 and AUTO_FILE not in m.fs, f'a failed save: -1, still off ({t}, {s})')
    m = auto_machine(); auto_setting(m); m.log = []
    auto_setting(m); r = hear(m); wait(m, r, 300)
    expect(opens(m, AUTO_FILE) == 0, 'the file is read once, not by every look')
    # a flip is seen by the next look at the conditions
    m = auto_machine(auto=False); r = hear(m)
    expect(until_job(m, r, 2 * WAIT) is None and sau(m, 'pending') == 1, 'off: a listen waits, nothing is uploaded')
    auto_toggle(m)
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP, f'switched on: the listen that waited over ten minutes is uploaded at the next look, within a minute ({t} s)')
    finish(m, r); r = hear(m, 1); auto_toggle(m)
    expect(until_job(m, r, 2 * WAIT) is None and sau(m, 'pending') == 1 and quiet(m), 'switched off again: the next listen waits')


def auto_idle_tests(ctx):
    """What the poll pays for the automatic upload: nothing while Auto Upload is off or no listen waits; nothing at boot."""
    expect = ctx.expect
    # the reference: a machine without an account and without the switch, a track paused for half an hour, a look a second
    ref = auto_machine(auto=False, token=False); r = song(ref); look(ref, r, 0, 300, 1000); ref.log = []
    wait(ref, r, 1800, 1)
    base = lnames(ref)
    expect(set(base) <= {'get_playtimeandlength'} and len(base) == 1800, f'(a look of a paused track asks the player its position and nothing else: {sorted(set(base))})')
    # Auto Upload on, an account, a log from an earlier boot, Wi-Fi: nothing waits from this boot, so the poll does nothing more than the reference
    m = auto_machine(old=range(5)); r = song(m); look(m, r, 0, 300, 1000); m.log = []
    wait(m, r, 1800, 1)
    expect(lnames(m) == base and sau(m, 'set') == 0, 'on with no listen logged this boot: the same calls as without it, a look a second for half an hour; the setting file is not even read')
    # Auto Upload off, a listen waiting: the setting is read once, by the first look after the listen; then the same calls
    m = auto_machine(auto=False); r = hear(m)
    look(m, r, dt=1000)
    expect(opens(m, AUTO_FILE) == 1 and sau(m, 'pending') == 1 and sau(m, 'set') == 1, 'off with a listen waiting: the first look reads the switch\'s file, once')
    m.log = []; wait(m, r, 1800, 1)
    expect(lnames(m) == base and threads(m) == 0, f'off: every later look makes the reference\'s calls and no other (no file, no Wi-Fi question, no thread) ({sorted(set(lnames(m)) - set(base))})')
    # Scrobbling off: nothing is counted, so nothing is asked at all
    m = auto_machine(on=False, old=range(5)); r = song(m); look(m, r, 0, 300, 1000); m.log = []   # (the first look reads the Scrobbling switch)
    for p in range(10, 301, 10): look(m, r, p, 300, 10000)
    wait(m, r, 1800)
    expect(not m.log and sau(m, 'pending') == 0, f'Scrobbling off, Auto Upload on: the poll makes no call at all ({sorted(set(lnames(m)))})')
    # on, a listen waiting, the Wi-Fi down: one look at the conditions a minute, each a window lookup and the Wi-Fi's state, no file
    m = auto_machine(); r = hear(m); m.wifi = -1; wait(m, r, WAIT + EVAL, 1); m.log = []
    wait(m, r, 600, 1)
    asked = lnames(m).count('get_wifisignal')
    expect(9 <= asked <= 10 and set(lnames(m)) == {'get_playtimeandlength', 'get_wifisignal'} and threads(m) == 0, f'the conditions are looked at once a minute: {asked} Wi-Fi questions in ten minutes of looks a second, no file opened ({sorted(set(lnames(m)))})')
    # the boot path (the tag reader's hook): the automatic upload is not there
    mp = '/mnt/mmc/Music/Boards of Canada/Music Has the Right to Children/03 - Roygbiv.flac'
    tags = dict(title='Roygbiv (Remastered 2013)', artist='Boards of Canada', album='Music Has the Right to Children')
    a = auto_machine(cls=podcasts.ID3, old=range(5)).count(); a.parse(mp, **tags)
    b = machine(lambda: podcasts.ID3(stock=True)).count(); b.parse(mp, **tags)
    expect(a.icount - b.icount < 4000 and a.names() == b.names() and not [c for c in a.calls if c[0] == 'open' and c[1] in (AUTO_FILE, SU.INI, SU.INI_TMP, LOG)],
           f'a music start at boot with Auto Upload on, an account and a log: {a.icount - b.icount} instructions more than stock, the stock calls and no other; no file of ours is opened, no thread')


def auto_start_tests(ctx):
    """The listens counted, the ten minutes, the upload and its silent end."""
    expect = ctx.expect
    m = auto_machine(old=range(3)); r = hear(m)
    expect(sau(m, 'pending') == 1 and threads(m) == 0, 'a listen logged: one waits, nothing starts yet')
    t = until_job(m, r, 2 * WAIT)
    expect(t is not None and WAIT <= t <= WAIT + EVAL + STEP and threads(m) == 1, f'the upload starts once the listen is ten minutes old, at the next look at the conditions ({t} s)')
    expect(SU.owner(m) == SU.AUTO and SU.kind(m) == SU.UPLOAD and SU.busy(m) == 1 and sau(m, 'job') == 1, 'it is the automatic upload\'s job')
    wait(m, r, 120)
    expect(threads(m) == 1 and 'pthread_join' not in lnames(m) and SU.busy(m) == 1, 'while it runs the looks only ask whether it is over')
    finish(m, r)
    expect('pthread_join' in lnames(m) and SU.busy(m) == 0 and sau(m, 'job') == 0 and sau(m, 'pending') == 0 and sau(m, 'fail') == 0, 'over: the next look collects it; nothing waits')
    expect(len(m.site.reqs) == 1 and len(m.site.listens()) == 4 and m.fs[LOG] == HEADER.encode() and len(m.fs[SU.SENT].decode().splitlines()) == 4,
           f'the whole log went: the three listens of earlier boots with this one ({len(m.site.listens())})')
    expect(quiet(m) and get_wifi_only(m), 'no toast, no timer, no keep-awake, no widget: nothing is shown; the Wi-Fi is asked its state and nothing else')
    expect(until_job(m, r, 4 * RETRY) is None, 'nothing more waits: two hours of looks start nothing')
    r = hear(m, 1)
    t = until_job(m, r, 2 * WAIT)
    expect(t is not None and WAIT <= t <= WAIT + EVAL + STEP, f'the next listen: the next upload, ten minutes later ({t} s)')
    finish(m, r)
    expect(len(m.site.listens()) == 5 and m.fs[LOG] == HEADER.encode(), 'with that listen alone')
    # several listens: one upload
    m = auto_machine(); r = hear(m, 0); r = hear(m, 1); r = hear(m, 2)
    expect(sau(m, 'pending') == 3 and threads(m) == 0, 'three tracks in a row (seven and a half minutes): three wait, no upload a track')
    t = until_job(m, r, WAIT)
    expect(t is not None and t <= WAIT - 300 + EVAL + STEP, f'ten minutes after the first of them: one upload ({t} s after the third)')
    finish(m, r)
    expect(len(m.site.reqs) == 1 and len(m.site.listens()) == 3 and sau(m, 'pending') == 0, 'the three in one request')
    # a listen logged while the upload runs still waits
    m = auto_machine(); r = hear(m, 0); until_job(m, r, 2 * WAIT); job = m.job
    r = hear(m, 1); m.job = job
    expect(sau(m, 'pending') == 2 and sau(m, 'took') == 1, '(a second listen is logged while the upload runs)')
    finish(m, r)
    expect(sau(m, 'pending') == 1, 'the upload\'s end takes off what waited at its start: the new listen still waits')
    t = until_job(m, r, 2 * WAIT)
    expect(t is not None and t <= WAIT, f'and has its upload, ten minutes after that start at the latest ({t} s)')
    finish(m, r)
    expect(sau(m, 'pending') == 0 and until_job(m, r, 2 * RETRY) is None and quiet(m), 'then nothing waits')
    # the music stops while the upload runs: a look without a track collects it too
    m = auto_machine(); r = hear(m); until_job(m, r, 2 * WAIT)
    SU.call(m, m.job[0], a0=m.job[1], count=1 << 40)
    look(m, 0, dt=1000)
    expect(SU.busy(m) == 0 and sau(m, 'pending') == 0 and quiet(m), 'a look with no track playing collects a finished upload')


def get_wifi_only(m): return not [n for n in set(lnames(m)) if 'wifi' in n.lower() and n != 'get_wifisignal']


def auto_gate_tests(ctx):
    """Every condition: no account, no Wi-Fi, USB mode, the kill switch, no card. Nothing starts, and the upload catches up when the condition is gone; an account written on a computer is used without a reboot."""
    expect = ctx.expect
    late = WAIT + 20 * 60   # a listen that has waited half an hour
    # no account
    m = auto_machine(token=False); r = hear(m)
    expect(until_job(m, r, late) is None and threads(m) == 0 and sau(m, 'fail') == 0 and 1 <= opens(m, SU.INI) <= late // EVAL + 1 and SU.INI not in m.fs and not [c for c in SU.wrote(m) if c[1].startswith(SU.INI)],
           f'no token: nothing starts; the card\'s scrobble.ini is looked for once a look at the conditions (a minute), not at every poll, and never made ({opens(m, SU.INI)} looks in {late} s)')
    m.fs[SU.INI] = SU.ini().encode()
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP, f'a scrobble.ini with a token is put on the card: the upload catches up within a minute ({t} s)')
    finish(m, r)
    expect(sau(m, 'pending') == 0 and quiet(m), 'and goes through')
    # the Wi-Fi, USB mode
    for what, on, off in (('the Wi-Fi not connected (-1)', lambda m: setattr(m, 'wifi', -1), lambda m: setattr(m, 'wifi', 4)), ('the Wi-Fi without a signal (0)', lambda m: setattr(m, 'wifi', 0), lambda m: setattr(m, 'wifi', 3)),
                          ('stock\'s USB mode window', lambda m: m.windows.update({'usbmode_page': 1}), lambda m: m.windows.pop('usbmode_page'))):
        m = auto_machine(); r = hear(m); on(m)
        expect(until_job(m, r, late) is None and threads(m) == 0 and sau(m, 'pending') == 1 and sau(m, 'fail') == 0, f'{what}: nothing starts, the listen waits')
        expect(get_wifi_only(m) and opens(m, LOG) == 1 and opens(m, SU.INI) == 0, f'{what}: the Wi-Fi is never switched on, the log is not read, nor the card\'s scrobble.ini')
        off(m)
        t = until_job(m, r, 2 * EVAL)
        expect(t is not None and t <= EVAL + STEP, f'{what}, then gone: the upload catches up within a minute ({t} s)')
        finish(m, r)
        expect(sau(m, 'pending') == 0 and len(m.site.listens()) == 1 and quiet(m), f'{what}: and goes through, silently')
    # what scrobup_start refuses: tried again half an hour later, not every minute
    for what, on, off in (('the kill switch', lambda m: m.present.add(KILL), lambda m: m.present.discard(KILL)),):
        m = auto_machine(); r = hear(m); on(m)
        expect(until_job(m, r, WAIT + EVAL + STEP) is None and threads(m) == 0 and sau(m, 'fail') == 1, f'{what}: the start is refused, no thread')
        off(m)
        t = until_job(m, r, 2 * RETRY)
        expect(t is not None and RETRY - EVAL - 2 * STEP <= t <= RETRY + EVAL + STEP, f'{what}, then gone: tried again half an hour after the refusal, not sooner ({t} s)')
        finish(m, r)
        expect(sau(m, 'pending') == 0 and sau(m, 'fail') == 0 and quiet(m), f'{what}: and goes through')
    # no mounted card is no token (the account is on the card): not a failure, looked at again a minute later
    m = auto_machine(); r = hear(m); m.card_mounted = False
    expect(until_job(m, r, late) is None and threads(m) == 0 and sau(m, 'fail') == 0 and not [c for c in m.log if c[0] == 'open' and c[1].startswith('/mnt/mmc/scrobble')], 'no mounted card: nothing starts, and nothing under the mount point is opened')
    m.card_mounted = True
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP, f'the card back: the upload catches up within a minute ({t} s)')
    finish(m, r)
    expect(sau(m, 'pending') == 0 and quiet(m), 'and goes through')
    # the account written on a computer over USB while the player is on: used when the card comes back, without a reboot
    m = auto_machine(token=False); r = hear(m)
    expect(until_job(m, r, WAIT + 2 * EVAL) is None, '(no account yet: nothing starts)')
    m.windows['usbmode_page'] = 1; m.card_mounted = False; m.log = []
    expect(until_job(m, r, 5 * EVAL) is None and not [c for c in m.log if c[0] in ('open', 'statfs') and c[1].startswith('/mnt/mmc')], 'USB mode: the computer has the card; the looks do not touch the mount point')
    m.fs[SU.INI] = b'[LISTENBRAINZ]\r\nTOKEN=' + SU.TOKEN.encode() + b'\r\n'
    m.windows.pop('usbmode_page'); m.card_mounted = True
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP and m.job, f'scrobble.ini written on the computer, the card back: the automatic upload starts within a minute ({t} s)')
    finish(m, r)
    expect(sau(m, 'pending') == 0 and m.site.reqs[-1]['heads'][0] == 'Authorization: Token ' + SU.TOKEN and quiet(m), 'with the file\'s token, silently')
    # a usable token: the looks before the upload is due read nothing from the card
    m = auto_machine(); r = hear(m); m.log = []
    wait(m, r, WAIT - EVAL)
    expect(opens(m, SU.INI) == 0 and not [c for c in m.log if c[0] == 'statfs'], 'while the listen is under ten minutes old no look reads the card\'s scrobble.ini or asks for the card')
    t = until_job(m, r, 3 * EVAL)
    expect(t is not None and 1 <= opens(m, SU.INI) <= 2, f'the look that starts the upload reads it (the gate, then the start): {opens(m, SU.INI)} reads')
    # any service: Last.fm alone starts the automatic upload
    m = auto_machine(token=False); m.fs[SU.INI] = SU.lf_ini().encode(); m.site.answers = SU.Lastfm(); r = hear(m)
    t = until_job(m, r, late)
    expect(t is not None and t <= WAIT + EVAL, f'a Last.fm account and no ListenBrainz token: the automatic upload starts ({t} s)')
    finish(m, r)
    expect(SU.methods(m) == ['getMobileSession', 'scrobble'] and sau(m, 'pending') == 0 and m.fs[LOG] == HEADER.encode() and quiet(m), f'and goes to Last.fm, silently ({SU.methods(m)})')
    # the only account refused: nothing more starts
    m = auto_machine(token=False); m.fs[SU.INI] = SU.lf_ini().encode(); m.site.answers = SU.Lastfm(auth=4); r = hear(m)
    until_job(m, r, late); finish(m, r); m.log = []
    expect(until_job(m, r, late) is None and threads(m) == 0 and sau(m, 'fail') == 0 and sau(m, 'pending') == 1 and quiet(m), 'Last.fm refuses the credentials and there is no other service: no automatic upload while that stands')
    m.fs[SU.INI] = SU.lf_ini(pw='fixed').encode(); m.site.answers.auth = None
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP, f'another password written into the file: the upload starts within a minute ({t} s)')
    # one of two refused: the other still uploads, by itself
    for what, svc, urls in (('Last.fm', SU.Lastfm(auth=4), [SU.URL]), ('ListenBrainz', SU.Lastfm(lb={'code': 401}), [SU.LF_URL, SU.LF_URL])):
        m = auto_machine(); m.fs[SU.INI] = (SU.ini(name='rob') + SU.lf_ini()).encode(); m.site.answers = svc; r = hear(m)
        until_job(m, r, late); finish(m, r); n = len(m.site.reqs)
        expect(sau(m, 'pending') == 1 and sau(m, 'fail') == 0 and len(lines(m)) == 1, f'{what} refuses its account in an automatic upload of both: the listen stays')
        t = until_job(m, r, 2 * EVAL)
        expect(t is not None and t <= EVAL + STEP, f'{what} refused: the next look starts an upload for the other service ({t} s)')
        finish(m, r)
        expect([q['url'] for q in m.site.reqs[n:]] == urls and sau(m, 'pending') == 0 and m.fs[LOG] == HEADER.encode() and quiet(m), f'{what} refused: the listen goes to the other one and leaves the log ({[q["url"] for q in m.site.reqs[n:]]})')


def auto_outcome_tests(ctx):
    """Each result, silently: done, a failure and its retry, a refused token, a service that takes nothing."""
    expect = ctx.expect
    # a failure: the log stays, the next try half an hour later
    for what, kw, prep in (('a 500', dict(answers=[{'code': 500}]), None), ('no connection', dict(answers=[{'rc': 7, 'code': 0}]), None), ('a 429', dict(answers=[{'code': 429}]), None),
                           ('a card that does not take the new log', {}, lambda m: m.fail.add(('rename', LOG)))):
        m = auto_machine(**kw); r = hear(m)
        if prep: prep(m)
        until_job(m, r, 2 * WAIT); finish(m, r)
        expect(sau(m, 'fail') == 1 and sau(m, 'pending') == 1 and sau(m, 'stop') == 0 and len(lines(m)) == 1 and SU.busy(m) == 0, f'{what}: collected, the listen is still in the log and still waits')
        m.fail.clear(); m.site.answers = [{}]
        t = until_job(m, r, 2 * RETRY)
        expect(t is not None and RETRY - STEP <= t <= RETRY + EVAL + STEP and threads(m) == 2, f'{what}: the next try no sooner than half an hour later ({t} s)')
        finish(m, r)
        expect(sau(m, 'fail') == 0 and sau(m, 'pending') == 0 and m.fs[LOG] == HEADER.encode() and SU.invalid(m) == 0 and quiet(m), f'{what}: which goes through; never a toast')
    # a failure, then a listen: the retry time holds
    m = auto_machine(answers=[{'code': 500}]); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    r = hear(m, 1)
    t = until_job(m, r, 2 * RETRY)
    expect(t is not None and t >= RETRY - 151 - STEP and sau(m, 'took') == 2, f'a new listen after a failure does not bring the retry forward ({t} s after it)')
    # the token refused: Invalid Token, and no automatic upload until the token changes
    for how, fixed in (('in a plain file', SU.ini('a-new-token').encode()), ('in a file with a comment, CRLF and lower case', b'; fixed\r\n[listenbrainz]\r\ntoken = a-new-token\r\n')):
        m = auto_machine(answers=[{'code': 401}]); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
        expect(SU.invalid(m) == 1 and sau(m, 'fail') == 0 and len(lines(m)) == 1 and SU.ini_of(m) == SU.ini(name='rob').encode(), 'a 401: Invalid Token is set (the rows show it), the token and the log are kept')
        r = hear(m, 1)
        expect(until_job(m, r, 2 * RETRY + WAIT) is None and threads(m) == 1, 'and no automatic upload starts again, whatever is played')
        m.site.answers = [{}]
        m.fs[SU.INI] = fixed
        t = until_job(m, r, 2 * EVAL)
        expect(SU.invalid(m) == 0 and t is not None and t <= EVAL + STEP, f'another token written on a computer {how}: the uploads resume within a minute, without a reboot ({t} s)')
        finish(m, r)
        expect(sau(m, 'pending') == 0 and m.site.reqs[-1]['heads'][0] == 'Authorization: Token a-new-token' and len(m.site.reqs[-1]['json']['payload']) == 2 and quiet(m), 'with the new token, both listens')
    m = auto_machine(answers=[{'code': 401}]); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    del m.fs[SU.INI]
    expect(until_job(m, r, 2 * RETRY) is None and SU.invalid(m) == 0, 'the file deleted on a computer: no account, so nothing starts, and not invalid')
    # the service takes nothing (every listen refused): no more automatic uploads this boot
    m = auto_machine(answers=[{'code': 400}], old=range(2)); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    expect(sau(m, 'stop') == 1 and SU.rejected(m) == 3 and m.fs[LOG] == HEADER.encode() and len(m.fs[SU.REJ].decode().splitlines()) == 3, 'every listen answered 400: the run moved three lines to .rejected, and the automatic upload stops')
    r = hear(m, 1); r = hear(m, 2)
    expect(until_job(m, r, 2 * RETRY + WAIT) is None and len(lines(m)) == 2 and len(m.fs[SU.REJ].decode().splitlines()) == 3 and quiet(m), 'later listens stay in the log: nothing drains it into .rejected run after run')
    m.site.answers = [{}]
    expect(SU.upload(m, SU.UI) == (SU.OK, 2) and m.fs[LOG] == HEADER.encode(), 'a manual upload is not affected')
    expect(until_job(m, hear(m, 3), 2 * RETRY) is None and sau(m, 'stop') == 1, 'and does not start the automatic ones again (until the next boot)')
    # some refused, some taken: not a reason to stop
    m = auto_machine(answers=SU.judge([900000]), old=(900000, 900001)); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    expect(sau(m, 'stop') == 0 and SU.rejected(m) == 1 and sau(m, 'pending') == 0 and m.fs[SU.REJ].decode() == SU.line(900000), 'one listen refused, two taken: the upload is done and the automatic uploads go on')
    r = hear(m, 1)
    t = until_job(m, r, 2 * WAIT)
    expect(t is not None and quiet(m), 'the next listen has its upload')
    # a run cut off (standby stops the Wi-Fi): a failure like any other
    m = auto_machine(answers=[{}, {'rc': 28, 'code': 0}], old=range(60)); r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    expect(sau(m, 'fail') == 1 and sau(m, 'stop') == 0 and len(lines(m)) == 11, 'a timeout after the first batch: 50 listens have left, the rest waits for the retry')


def auto_owner_tests(ctx):
    """Whose job a poll is: the automatic upload never polls the pages' job, never writes the card's scrobble.ini, and its own result is collected by anyone who calls
    scrobble_auto_collect."""
    expect = ctx.expect
    # the pages' upload runs when the automatic one is due
    m = auto_machine(old=range(3)); r = hear(m)
    expect(SU.start(m, SU.UI) == 1, '(the user starts an upload)')
    ui = m.thread
    expect(until_job(m, r, WAIT + 5 * EVAL) is None and 'pthread_join' not in lnames(m) and SU.busy(m) == 1 and sau(m, 'job') == 0, 'the user\'s upload runs: the automatic one does not start, and does not poll')
    SU.call(m, ui[0], a0=ui[1], count=1 << 40)
    expect(until_job(m, r, 5 * EVAL) is None and 'pthread_join' not in lnames(m) and SU.busy(m) == 1 and SU.owner(m) == SU.UI, 'it is over and not polled by the pages yet: the looks leave its result alone')
    SU.call(m, PSYMS['scrobble_auto_collect'], count=1 << 24)
    expect(SU.busy(m) == 1 and 'pthread_join' not in lnames(m), 'scrobble_auto_collect too')
    expect(SU.poll(m) == (SU.OK, 4), 'the pages get their result, whole')
    t = until_job(m, r, 2 * EVAL)
    expect(t is not None and t <= EVAL + STEP and SU.owner(m) == SU.AUTO, f'then the automatic upload has its turn ({t} s)')
    finish(m, r)
    expect(sau(m, 'pending') == 0 and len(m.site.reqs) == 1 and quiet(m), 'and finds nothing left to send')
    # the pages' check
    m = auto_machine(answers=[SU.answer('rob')]); r = hear(m)
    expect(SU.check_start(m, SU.UI) == 1, '(a check of the token runs)')
    ui = m.thread; SU.call(m, ui[0], a0=ui[1], count=1 << 40)
    expect(until_job(m, r, WAIT + 5 * EVAL) is None and SU.busy(m) == 1 and SU.kind(m) == SU.CHECK and 'pthread_join' not in lnames(m), 'a check that is over and not polled: not polled here either')
    expect(SU.poll(m) == (SU.OK, 0), 'its result is the pages\'')
    # scrobble_auto_collect: what the pages call
    m = auto_machine(); r = hear(m); until_job(m, r, 2 * WAIT); m.log = []
    SU.call(m, PSYMS['scrobble_auto_collect'], count=1 << 24)
    expect(SU.busy(m) == 1 and sau(m, 'job') == 1 and 'pthread_join' not in lnames(m), 'while the automatic upload runs: nothing')
    SU.call(m, m.job[0], a0=m.job[1], count=1 << 40)
    SU.call(m, PSYMS['scrobble_auto_collect'], count=1 << 24)
    expect(SU.busy(m) == 0 and sau(m, 'job') == 0 and sau(m, 'pending') == 0 and 'pthread_join' in lnames(m) and quiet(m), 'over: collected and applied, without a word; the worker is free for the user')
    m.log = []
    SU.call(m, PSYMS['scrobble_auto_collect'], count=1 << 24)
    expect(not m.log, 'with no job: no call at all')
    m = auto_machine(answers=[{'code': 401}]); r = hear(m); until_job(m, r, 2 * WAIT)
    SU.call(m, m.job[0], a0=m.job[1], count=1 << 40)
    SU.call(m, PSYMS['scrobble_auto_collect'], count=1 << 24)
    expect(SU.invalid(m) == 1 and quiet(m), 'a refused token collected that way: Invalid Token, no toast')
    # the card's scrobble.ini is the user's: an automatic upload reads it and never writes it
    mine = b'; mine\r\n[LASTFM]\r\nUSER=me\r\nPASSWORD=secret\r\n[ListenBrainz]\r\nToken = ' + SU.TOKEN.encode() + b'\r\n'
    m = auto_machine(token=False); m.fs[SU.INI] = mine; r = hear(m); until_job(m, r, 2 * WAIT); finish(m, r)
    expect(m.fs.get(SU.INI) == mine and SU.INI_TMP not in m.fs and not [c for c in m.log if c[0] in ('write', 'rename', 'unlink') and c[1].startswith(SU.INI)] and m.site.reqs[0]['heads'][0] == 'Authorization: Token ' + SU.TOKEN,
           'an automatic upload with a hand-written scrobble.ini (no USER): its token is used, the file is not written (no check, no USER line), [LASTFM] is as it was')
    m = auto_machine(token=False); r = hear(m)
    expect(until_job(m, r, 2 * RETRY) is None and SU.INI not in m.fs and not [p for p in m.fs if 'listenbrainz' in p], 'and with no account nothing starts, and no account file is made anywhere')


SECTIONS = [setting_tests, rule_tests, step_tests, skip_tests, hook_tests, auto_setting_tests, auto_idle_tests, auto_start_tests, auto_gate_tests, auto_outcome_tests, auto_owner_tests]
