"""Library list hand-over (patch/libload.c, docs/modules/libload.md): loadLocalClassList frees the list it replaces before its query and hands the query's rows over without copying them.

ll_load, ll_assign, lib_deque_swap and lib_take_list run in Unicorn against the built demo; stock's own tail (0x4ee638 .. 0x4ee680) runs from the built demo with libcstl's
calls modelled, so the patched call site is exercised as stock reaches it. Stock's words and jump tables are checked against the stock demo, and a changed pin must refuse the build."""
import struct
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_S0, UC_MIPS_REG_S1, UC_MIPS_REG_GP
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

KILL = '/mnt/mmc/m1plus-off'
SHOW, PLAYLIST, TMP = pod.DATA['PDEQ_SHOWLIST'][0], pod.DATA['PDEQ_PLAYLIST'][0], pod.DATA['PDEQ_TOOLS_TMP'][0]
SIZE, SELF = pod.CSTL_DEQUE_SIZE, pod.CSTL_DEQUE_SELF
STUBS = {0x742fd0: 'deque_clear', 0x742610: 'deque_assign', 0x743590: 'deque_size'}   # demo's own stubs of the three libcstl calls of the tail (its GOT slots before binding)
TAIL, TAIL_END = 0x4ee638, 0x4ee680


class LLM(Machine):
    """The real lib_deque_swap on real deque_t-sized blocks; stock's loadLocalClassList behind the trampoline answers `stock_ret`."""
    COUNT = True

    def __init__(self):
        super().__init__()
        self.handlers.pop(PSYMS['lib_deque_swap'])
        self.handlers[PSYMS['stock_loadclass_trampoline']] = 'll_stock'
        for a, n in STUBS.items(): self.handlers[a] = n
        self.stock_ret = 7

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name in ('deque_clear', 'deque_assign', 'deque_size'):
            a0 = u.reg_read(UC_MIPS_REG_A0)
            # The first word is a synthetic backing-store token. The real MIPS swap moves it,
            # so these mocks follow the moved storage instead of the deque's unchanged address.
            items = self.items(a0)
            ret = 0
            if name == 'deque_clear':
                items.clear(); self.calls.append(('deque_clear', a0))
            elif name == 'deque_assign':
                items[:] = self.items(u.reg_read(UC_MIPS_REG_A1))
                self.calls.append(('deque_assign', len(items)))
            else:
                ret = len(items)
            u.reg_write(UC_MIPS_REG_V0, ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        if self.handlers.get(address) == 'll_stock':
            self.calls.append(('stock_load', u.reg_read(UC_MIPS_REG_A0)))
            u.reg_write(UC_MIPS_REG_V0, self.stock_ret); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
        return super()._hook(u, address, size, _)

    def new_deque(self, items=()):
        """A deque as _create_deque + deque_init leave it for this code: 0x14c bytes, the two container pointers at itself, a fill that tells the two apart."""
        h = self.alloc(SIZE)
        self.u.mem_write(h, bytes((h >> 3) + i & 0xff for i in range(SIZE)))
        self.setword(h, h)
        for off in SELF: self.setword(h + off, h)
        self.deques[h] = list(items)
        return h

    def body(self, h): return bytes(self.u.mem_read(h, SIZE))
    def items(self, h): return self.deques[self.word(h)]

    def tail(self, dst_slot):
        """Stock's tail of loadLocalClassList as the built demo has it, entered as the cases enter it: s1 = the destination's slot, s0 = &tools_pdeq_directory."""
        u = self.u
        self.calls = []
        u.reg_write(UC_MIPS_REG_SP, STACK - 0x40); sp = STACK - 0x40
        self.setword(sp + 0x10, pod.GP); self.setword(sp + 0x24, RET)
        u.reg_write(UC_MIPS_REG_GP, pod.GP); u.reg_write(UC_MIPS_REG_S1, dst_slot); u.reg_write(UC_MIPS_REG_S0, TMP); u.reg_write(UC_MIPS_REG_RA, 0)
        self.limit = 4000
        u.emu_start(TAIL, RET)
        assert u.reg_read(UC_MIPS_REG_PC) == RET, 'the tail did not return'
        return u.reg_read(UC_MIPS_REG_V0)


def swapped(m, a, b, before_a, before_b):
    """a holds what b held and b what a held, but for the container pointers, which are each deque's own again."""
    def own(h, was, other):
        want = bytearray(was)
        for off in SELF: struct.pack_into('<I', want, off, h)
        return m.body(h) == bytes(want) and all(m.word(h + off) == h for off in SELF) and was != m.body(other)
    return own(a, before_b, b) and own(b, before_a, a)


def run(ctx):
    expect = ctx.expect
    stock_demo = stock_demo_bytes()
    built = built_demo_bytes()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    jal = lambda target: (3 << 26) | (target >> 2)

    # 1. The build: the prologue and the call site are stock's in the stock demo, `j ll_load; nop` and `jal ll_assign` in the build; every pin is stock's and unchanged.
    expect(tuple(w(stock_demo, pod.LCL + 4 * i) for i in range(3)) == pod.LCL_PROLOGUE and pod.LCL == pod.FUNCTIONS['loadLocalClassList'][2] == 0x4ee504
           and w(built, pod.LCL) == ((2 << 26) | (PSYMS['ll_load'] >> 2)) and w(built, pod.LCL + 4) == 0,
           'loadLocalClassList\'s prologue is stock\'s in the stock demo and `j ll_load; nop` in the build')
    expect(w(stock_demo, pod.LCL_ASSIGN_SITE) == 0x0320f809 and w(built, pod.LCL_ASSIGN_SITE) == jal(PSYMS['ll_assign']), 'the tail\'s `jalr deque_assign` is `jal ll_assign` in the build')
    expect(all(w(stock_demo, a) == old for a, old, _ in pod.LCL_PINS) and all(w(built, a) == old for a, old, _ in pod.LCL_PINS if a != pod.LCL_ASSIGN_SITE),
           'every pinned word is stock\'s, in the stock demo and (but the site) in the build')
    expect(MANIFEST['hook_loadclass'] == {'addr': pod.LCL, 'target': PSYMS['ll_load']} and MANIFEST['hook_loadclass_assign'] == {'addr': pod.LCL_ASSIGN_SITE, 'target': PSYMS['ll_assign']},
           'the manifest records both edits')
    # the jump tables: which case each class takes, and that every class ll_load frees for ends at the show list (not the playlists' 0x4ee614, the online 0x4ee7b4, the unknown 0x4ee5a8)
    case = {0xf001: 0x4ee5bc}
    for (at, cases), first in zip(pod.LCL_TABLES, (0xf002, 0xff01)):
        got = tuple((x + pod.GP) & 0xffffffff for x in struct.unpack_from(f'<{len(cases)}I', stock_demo, pod.fileoff(stock_demo, at)))
        expect(got == cases, f'the jump table at {at:#x} is the pinned one')
        case.update({first + i: c for i, c in enumerate(cases)})
    expect(all(case.get(c) not in (None, 0x4ee614, 0x4ee7b4, 0x4ee5a8) for c in pod.LCL_LOCAL) and case[0xf00b] == 0x4ee614 and case[0xff23] == 0x4ee7b4,
           'every local class of LCL_LOCAL has a case of its own that ends at the show list')
    lib = open(os.path.join(WORK, 'rootfs', pod.LIBCSTL), 'rb').read()
    pod.check_libcstl_bytes(lib)
    bad = bytearray(lib); bad[pod.CSTL_SWAP + 0x124] ^= 1
    try: pod.check_libcstl_bytes(bytes(bad)); refused = False
    except (SystemExit, AssertionError, ValueError): refused = True
    expect(refused, 'a libcstl whose deque_swap differs from the pin refuses the build')

    # 2. lib_deque_swap: the two structs change sides, each deque's container pointers are its own, both pointers stay.
    m = LLM(); a, b = m.new_deque(), m.new_deque(); ba, bb = m.body(a), m.body(b)
    r = m.call(PSYMS['lib_deque_swap'], a0=a, a1=b)
    expect(r == 1 and swapped(m, a, b, ba, bb) and not m.calls, 'the exchange: 0x14c bytes each way, +0x124 / +0x140 each deque\'s own again, no call made')
    expect(m.icount < 1200, f'and it is a few hundred instructions whatever the lists hold ({m.icount})')
    for label, mk in (('the same deque twice', lambda m, a, b: (a, a)), ('a null deque', lambda m, a, b: (a, 0)), ('a null first deque', lambda m, a, b: (0, b)),
                      ('a first container pointer that is not the deque', lambda m, a, b: (m.setword(a + SELF[0], b), (a, b))[1]),
                      ('a second container pointer that is not the deque', lambda m, a, b: (m.setword(b + SELF[1], 0), (a, b))[1])):
        m = LLM(); a, b = m.new_deque(), m.new_deque(); x, y = mk(m, a, b); ba, bb = m.body(a), m.body(b)
        expect(m.call(PSYMS['lib_deque_swap'], a0=x, a1=y) == 0 and m.body(a) == ba and m.body(b) == bb, f'{label}: refused, nothing changed')

    # 3. ll_load: a local class frees the show list first, then stock's function runs with the class and its result is returned.
    m = LLM(); old = m.new_deque(); m.setword(SHOW, old); pl = m.new_deque([4]); m.setword(PLAYLIST, pl)
    for cls in range(0xeff0, 0xff40):
        m.deques[old] = [1, 2, 3]
        r = m.call(PSYMS['ll_load'], a0=cls)
        order = [c for c in m.calls if c[0] in ('deque_clear', 'stock_load')]
        if cls in pod.LCL_LOCAL:
            ok = r == 7 and order == [('deque_clear', old), ('stock_load', cls)] and ('access', KILL) in m.calls
        else:
            ok = r == 7 and order == [('stock_load', cls)] and m.deques[old] == [1, 2, 3]
        if not ok or cls in (0xf001, 0xf008, 0xf00b, 0xff23):
            expect(ok, f'class {cls:#x}: {"the old show list is cleared, then stock runs" if cls in pod.LCL_LOCAL else "stock alone (not a local show list class)"} ({order})')
        if m.deques[pl] != [4]: expect(False, f'class {cls:#x}: the playlist list is never touched')
    m = LLM(); old = m.new_deque([1]); m.setword(SHOW, old); m.present.add(KILL)
    expect(m.call(PSYMS['ll_load'], a0=0xf001) == 7 and [c for c in m.calls if c[0] in ('deque_clear', 'stock_load')] == [('stock_load', 0xf001)], f'with {KILL}: stock alone')
    m = LLM(); m.setword(SHOW, 0)
    expect(m.call(PSYMS['ll_load'], a0=0xf001) == 7 and 'deque_clear' not in m.names(), 'no show list yet: stock alone')
    m = LLM(); old = m.new_deque([1]); m.setword(old + SELF[0], 0); m.setword(SHOW, old)
    expect(m.call(PSYMS['ll_load'], a0=0xf001) == 7 and 'deque_clear' not in m.names(), 'a show list that is not an initialised deque: stock alone')
    m = LLM(); old = m.new_deque([1]); m.setword(SHOW, old); m.stock_ret = 0
    expect(m.call(PSYMS['ll_load'], a0=0xf008) == 0, 'stock\'s result is returned as it is (an empty list)')

    # 4. ll_assign: the destination takes the rows without a copy; stock's deque_assign with the kill switch or when the exchange is refused.
    m = LLM(); dst, rows = m.new_deque(), m.new_deque(); bd, br = m.body(dst), m.body(rows)
    m.call(PSYMS['ll_assign'], a0=dst, a1=rows)
    expect(swapped(m, dst, rows, bd, br) and 'deque_assign' not in m.names(), 'the destination holds the rows\' struct, the row deque the destination\'s (empty) one; nothing is copied')
    m = LLM(); dst, rows = m.new_deque(), m.new_deque([5, 6]); bd, br = m.body(dst), m.body(rows); m.present.add(KILL)
    m.call(PSYMS['ll_assign'], a0=dst, a1=rows)
    expect(m.body(dst) == bd and m.body(rows) == br and ('deque_assign', 2) in m.calls, f'with {KILL}: stock\'s deque_assign(dst, rows), nothing exchanged')
    m = LLM(); dst, rows = m.new_deque(), m.new_deque([5, 6]); m.setword(rows + SELF[1], 0); bd, br = m.body(dst), m.body(rows)
    m.call(PSYMS['ll_assign'], a0=dst, a1=rows)
    expect(m.body(dst) == bd and m.body(rows) == br and ('deque_assign', 2) in m.calls, 'a deque of another layout: stock\'s deque_assign')

    # 5. Stock's tail in the built demo: clear(dst), our hand-over with (dst, rows) as stock passed them to deque_assign, clear(rows), size(dst). For each destination slot.
    for slot, name in ((SHOW, 'the show list'), (PLAYLIST, 'the playlist list')):
        m = LLM(); dst, rows = m.new_deque(['old']), m.new_deque(['r1', 'r2', 'r3']); m.setword(slot, dst); m.setword(TMP, rows); br = m.body(rows)
        result = m.tail(slot)
        seq = [c for c in m.calls if c[0] in ('deque_clear', 'deque_assign', 'deque_size')]
        want = bytearray(br)
        for off in SELF: struct.pack_into('<I', want, off, dst)
        expect(result == 3 and m.items(dst) == ['r1', 'r2', 'r3'] and not m.items(rows)
               and seq == [('deque_clear', dst), ('deque_clear', rows)] and m.body(dst) == bytes(want) and m.word(slot) == dst and m.word(TMP) == rows,
               f'{name}: stock clears it, it takes the rows\' struct (no deque_assign), stock clears the row deque; both slots keep their pointers ({seq})')
    m = LLM(); dst, rows = m.new_deque(['old']), m.new_deque(['r1', 'r2']); m.setword(SHOW, dst); m.setword(TMP, rows); m.present.add(KILL); bd = m.body(dst)
    result = m.tail(SHOW)
    expect(result == 2 and m.items(dst) == ['r1', 'r2'] and not m.items(rows)
           and [c for c in m.calls if c[0] in ('deque_clear', 'deque_assign')] == [('deque_clear', dst), ('deque_assign', 2), ('deque_clear', rows)] and m.body(dst) == bd,
           f'with {KILL} the tail is stock\'s: clear, deque_assign, clear')

    # Repeated 47,000-row hand-overs: clearing the scratch deque must not clear the moved
    # records, and reloading must release the preceding result without any deep copy.
    m = LLM(); dst, rows = m.new_deque(), m.new_deque(); m.setword(SHOW, dst); m.setword(TMP, rows)
    for generation in range(4):
        records = list(range(generation * 47000, (generation + 1) * 47000))
        m.items(rows)[:] = records
        result = m.tail(SHOW)
        expect(result == 47000 and m.items(dst) == records and not m.items(rows) and 'deque_assign' not in m.names(),
               f'47,000 rows, reload {generation + 1}: all records survive the scratch clear with one owner and no deep copy')

    # 6. lib_take_list: a deque of our own with the list's struct; the list is left an empty deque. Refused: a copy, the list as it was.
    m = LLM(); lst = m.new_deque(['a', 'b']); bl = m.body(lst)
    d = m.call(PSYMS['lib_take_list'], a0=lst)
    want = bytearray(bl)
    for off in SELF: struct.pack_into('<I', want, off, d)
    expect(d and d != lst and m.body(d) == bytes(want) and m.items(d) == ['a', 'b'] and not m.items(lst)
           and all(m.word(lst + off) == lst for off in SELF) and ('_create_deque', 'stSongInfo') in m.calls and 'deque_assign' not in m.names(),
           'the new stSongInfo deque holds the list\'s struct, the list the new deque\'s; no copy')
    m = LLM(); lst = m.new_deque(['a', 'b']); m.setword(lst + SELF[0], 0); bl = m.body(lst)
    d = m.call(PSYMS['lib_take_list'], a0=lst)
    expect(d and m.body(lst) == bl and ('deque_assign', 2) in m.calls and m.deques[d] == ['a', 'b'], 'refused: the list is copied (deque_assign) and keeps its records')
    m = LLM(); lst = m.new_deque(['a']); m.deque_fail = True
    expect(m.call(PSYMS['lib_take_list'], a0=lst) == 0 and m.deques[lst] == ['a'], 'no memory for the deque: NULL, the list untouched')

    # 7. A changed pinned word or prologue refuses the build.
    for a, _, what in (pod.LCL_PINS[0], pod.LCL_PINS[-1]):
        img = bytearray(stock_demo); struct.pack_into('<I', img, pod.fileoff(img, a), w(stock_demo, a) ^ 0x100)
        try: pod.check_pins(img, pod.LCL_PINS); refused = False
        except (SystemExit, AssertionError, ValueError): refused = True
        expect(refused, f'a changed word at {a:#x} ({what}) refuses the build')
    img = bytearray(stock_demo); struct.pack_into('<I', img, pod.fileoff(img, pod.LCL), 0)
    try: pod.hook(img, pod.LCL, pod.LCL_PROLOGUE, PSYMS['ll_load'], 'll_load'); refused = False
    except (SystemExit, AssertionError, ValueError): refused = True
    expect(refused, 'a changed loadLocalClassList prologue refuses the build')
    img = bytearray(stock_demo); struct.pack_into('<I', img, pod.fileoff(img, pod.LCL_TABLES[0][0]), 0)
    try: pod.check_lcl_tables(img); refused = False
    except (SystemExit, AssertionError, ValueError): refused = True
    expect(refused, 'a changed jump table refuses the build')
