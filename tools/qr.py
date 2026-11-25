"""The QR code of the Wi-Fi Transfer page's address (patch/qr.c is a line-for-line port; docs/modules/wifi-transfer.md "QR code").

One symbol size only: version 2 (25 x 25 modules), error correction level M, one alphanumeric segment of at most QR_MAX characters
(0-9, A-Z, space and $%*+-./:), so "HTTP://255.255.255.255:8888" (27) always fits. The steps and the mask penalty follow ISO/IEC 18004
as Project Nayuki's QR Code generator (MIT) implements them; this is a fresh, reduced implementation, not a copy.
"""

SIZE, VERSION, DATA_CW, EC_CW, QR_MAX = 25, 2, 28, 16, 38
ALNUM = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'
ALIGN = 18                       # version 2's one alignment pattern centre (x and y)
ECL_M = 0                        # the format field's two bits for level M
N1, N2, N3, N4 = 3, 3, 40, 10    # the mask penalty weights


def gf_mul(a, b):
    """a * b in GF(2^8) modulo x^8 + x^4 + x^3 + x^2 + 1 (0x11D)."""
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((b >> i) & 1) * a
    return z & 0xFF


def rs_divisor(degree):
    out, root = [0] * (degree - 1) + [1], 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = gf_mul(out[j], root)
            if j + 1 < degree: out[j] ^= out[j + 1]
        root = gf_mul(root, 2)
    return out


def rs_remainder(data, div):
    out = [0] * len(div)
    for b in data:
        f = b ^ out.pop(0); out.append(0)
        for i, c in enumerate(div): out[i] ^= gf_mul(c, f)
    return out


def codewords(text):
    """The 44 codewords (28 data, 16 error correction), or None when the text is not alphanumeric or too long."""
    if len(text) > QR_MAX or any(c not in ALNUM for c in text): return None
    bits = []
    put = lambda v, n: bits.extend((v >> i) & 1 for i in range(n - 1, -1, -1))
    put(0b0010, 4); put(len(text), 9)
    for i in range(0, len(text) - 1, 2): put(ALNUM.index(text[i]) * 45 + ALNUM.index(text[i + 1]), 11)
    if len(text) % 2: put(ALNUM.index(text[-1]), 6)
    cap = DATA_CW * 8
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    data = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < DATA_CW: data.append(pad); pad ^= 0xEC ^ 0x11
    return data + rs_remainder(data, rs_divisor(EC_CW))


def masked(m, x, y):
    return (((x + y) % 2 == 0), (y % 2 == 0), (x % 3 == 0), ((x + y) % 3 == 0), ((x // 3 + y // 2) % 2 == 0),
            (x * y % 2 + x * y % 3 == 0), ((x * y % 2 + x * y % 3) % 2 == 0), (((x + y) % 2 + x * y % 3) % 2 == 0))[m]


def format_bits(mask):
    data = ECL_M << 3 | mask
    rem = data
    for _ in range(10): rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return (data << 10 | rem) ^ 0x5412


class Symbol:
    def __init__(self):
        self.mod = [[0] * SIZE for _ in range(SIZE)]
        self.fn = [[0] * SIZE for _ in range(SIZE)]

    def set_fn(self, x, y, dark):
        self.mod[y][x], self.fn[y][x] = int(dark), 1

    def function_patterns(self):
        for i in range(SIZE): self.set_fn(6, i, i % 2 == 0); self.set_fn(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (SIZE - 4, 3), (3, SIZE - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if 0 <= cx + dx < SIZE and 0 <= cy + dy < SIZE: self.set_fn(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
        for dy in range(-2, 3):
            for dx in range(-2, 3): self.set_fn(ALIGN + dx, ALIGN + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)

    def draw_format(self, mask):
        b = format_bits(mask); bit = lambda i: (b >> i) & 1
        for i in range(6): self.set_fn(8, i, bit(i))
        self.set_fn(8, 7, bit(6)); self.set_fn(8, 8, bit(7)); self.set_fn(7, 8, bit(8))
        for i in range(9, 15): self.set_fn(14 - i, 8, bit(i))
        for i in range(8): self.set_fn(SIZE - 1 - i, 8, bit(i))
        for i in range(8, 15): self.set_fn(8, SIZE - 15 + i, bit(i))
        self.set_fn(8, SIZE - 8, 1)

    def place(self, cw):
        i, right = 0, SIZE - 1
        while right >= 1:
            if right == 6: right = 5
            for vert in range(SIZE):
                for j in range(2):
                    x = right - j
                    y = SIZE - 1 - vert if ((right + 1) & 2) == 0 else vert
                    if not self.fn[y][x] and i < len(cw) * 8:
                        self.mod[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1; i += 1
            right -= 2

    def apply_mask(self, m):
        for y in range(SIZE):
            for x in range(SIZE):
                if not self.fn[y][x] and masked(m, x, y): self.mod[y][x] ^= 1

    def penalty(self):
        score = 0
        lines = [self.mod[y] for y in range(SIZE)] + [[self.mod[y][x] for y in range(SIZE)] for x in range(SIZE)]
        for line in lines:
            color, run, hist = 0, 0, [0] * 7
            for v in line:
                if v == color:
                    run += 1
                    if run == 5: score += N1
                    elif run > 5: score += 1
                else:
                    add_history(run, hist)
                    if not color: score += finder_count(hist) * N3
                    color, run = v, 1
            if color: add_history(run, hist); run = 0
            add_history(run + SIZE, hist)
            score += finder_count(hist) * N3
        for y in range(SIZE - 1):
            for x in range(SIZE - 1):
                if self.mod[y][x] == self.mod[y][x + 1] == self.mod[y + 1][x] == self.mod[y + 1][x + 1]: score += N2
        dark, total = sum(map(sum, self.mod)), SIZE * SIZE
        return score + ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * N4


def add_history(run, hist):
    if hist[0] == 0: run += SIZE   # the light border before the first run
    hist[1:] = hist[:6]; hist[0] = run


def finder_count(h):
    n = h[1]
    core = n > 0 and h[2] == h[4] == h[5] == n and h[3] == n * 3
    return int(core and h[0] >= n * 4 and h[6] >= n) + int(core and h[6] >= n * 4 and h[0] >= n)


def encode(text, mask=-1):
    """The symbol's rows (SIZE lists of 0 / 1, 1 dark) for text with the mask given, or the one of least penalty (-1); None when it does not fit."""
    cw = codewords(text)
    if cw is None: return None
    s = Symbol(); s.function_patterns(); s.place(cw)
    if mask < 0:
        best = None
        for m in range(8):
            s.apply_mask(m); s.draw_format(m)
            p = s.penalty()
            if best is None or p < best[0]: best = (p, m)
            s.apply_mask(m)
        mask = best[1]
    s.apply_mask(mask); s.draw_format(mask)
    return s.mod


def address_text(ip):
    """What the page encodes for an address: the URL in capitals (the alphanumeric set has no small letters; a browser takes HTTP://)."""
    return f'HTTP://{ip}:8888'
