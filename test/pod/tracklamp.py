"""Sample Rate RGB classification and volume-scaled channel mixing (patch/tracklamp.c)."""
from harness import *  # noqa: F401,F403


def sample(m, name, rate, depth, codec, volume=85):
    record = m.record(name=name, path='/mnt/mmc/' + name)
    info = m.alloc(52)
    m.u.mem_write(info, bytes(52))
    m.setword(info + 4, rate)
    m.u.mem_write(info + 16, codec.encode('ascii')[:15].ljust(16, b'\0'))
    m.setword(info + 48, depth)
    return m.call(PSYMS['formatlamp_rgb_levels'], a0=record, a1=info, a2=volume)


def packed(red, green, blue):
    return red << 16 | green << 8 | blue


def run(ctx):
    expect = ctx.expect
    m = Machine()
    cases = (
        ('lossy', 'track.mp3', 44100, 16, 'mp3', packed(17, 0, 0)),
        ('PCM 16/44.1', 'track.flac', 44100, 16, 'flac', packed(17, 0, 0)),
        ('PCM 24/44.1', 'track.flac', 44100, 24, 'flac', packed(10, 0, 7)),
        ('PCM 24/48', 'track.flac', 48000, 24, 'flac', packed(3, 0, 14)),
        ('PCM 24/88.2', 'track.flac', 88200, 24, 'flac', packed(0, 0, 17)),
        ('PCM 24/96', 'track.flac', 96000, 24, 'flac', packed(0, 3, 14)),
        ('PCM 24/176.4', 'track.flac', 176400, 24, 'flac', packed(0, 7, 10)),
        ('PCM 24/192', 'track.flac', 192000, 24, 'flac', packed(0, 17, 0)),
        ('DSD64', 'track.dsf', 2822400, 1, 'DSD', packed(10, 0, 7)),
        ('DSD128', 'track.dsf', 5644800, 1, 'DSD128', packed(0, 3, 14)),
        ('DSD256', 'track.dsf', 11289600, 1, 'DSD256', packed(0, 7, 10)),
        ('DSD512', 'track.dsf', 22579200, 1, 'DSD512', packed(0, 17, 0)),
    )
    for label, name, rate, depth, codec, want in cases:
        expect(sample(m, name, rate, depth, codec) == want, f'{label}: requested RGB proportions at full level')
    expect(sample(m, 'track.flac', 48000, 24, 'flac', 50) == packed(2, 0, 8),
           'volume scales the 20/80 red-blue mix without changing its target proportions')
    expect(sample(m, 'track.dsf', 11289600, 1, 'DSD256', 50) == packed(0, 4, 6),
           'volume scales the 40/60 green-blue mix without changing its target proportions')
    expect(sample(m, 'track.flac', 48000, 24, 'flac', 0) == 0,
           'volume zero turns every mixed color off')
    expect(sample(m, 'track.flac', 192000, 24, 'flac', 100) == packed(0, 17, 0),
           'volume above 85 stays at full channel level')
