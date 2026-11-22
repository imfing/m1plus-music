#!/usr/bin/env python3
"""The geometry of M1+ Music's own QWERTY keyboard (patch/keyboard.c, docs/modules/keyboard.md), in one place.

tools/pod_ui.py builds ui/m1plus_keyboard.bin from it (the lowercase page), the tests check every page's widget moves in the payload against it,
and tools/preview/preview_keyboard.py draws all pages from it. patch/keyboard.c repeats the arithmetic (x0 = (320 - n w - (n - 1) 3 + 1) / 2) and the strings;
test/pod/keyboard.py compares the two.

iPhone OS 1 proportions on the M1 Plus' 320 px screen: the pad is 180 px high at the bottom of the window (450 px under the 30 px status bar: the
bottom of the 480 px screen), 6 px of padding above and under four rows at a 44 px pitch, keys 36 px high. Letter keys are 29 px wide with 3 px
gaps (ten across: 317 px, a margin of 1.5 px: 2 on the left, 1 on the right), rows of nine and seven are centred, shift and delete are 40 wide at the
edges, the bottom row is 123 (74), space (163) and Search (74).
"""
SCREEN_W = 320
KB_H = 180
KB_PAD, KB_PITCH, KB_KH, KB_KW, KB_GAP = 6, 44, 36, 29, 3
KB_FN_W, KB_MODE_W, KB_NUM_KW = 40, 74, 41   # shift / delete / #+=; 123 / ABC and Search; the keys of the third row on the 123 and #+= pages
KB_EDGE = 2                                  # the left margin of a full row (the right one is 1)
KB_LANG_W = 40                               # the language key of row four (only with more than one keyboard enabled): the space key gives it the room
KB_KEYS = 26                                 # char key widgets (the letter pages need 26: 10 + 9 + 7)
KB_MAX = 63                                  # bytes of text

# Colours: white and grey only, no accent anywhere.
from pod_roles import INK_RGB, PLACEHOLDER_RGB, SURFACE_RGB
KB_BG, KB_KEY, KB_KEY_DOWN = SURFACE_RGB, '#4A4A4E', '#6E6E73'
KB_FN, KB_FN_DOWN = '#2E2E32', '#4A4A4E'
KB_ON, KB_ON_DOWN = '#E5E5EA', '#C7C7CC'     # shift while it is on: a light key with a dark arrow
KB_POP = '#6E6E73'
KB_INK, KB_DARK_INK, KB_GREY = INK_RGB, SURFACE_RGB, PLACEHOLDER_RGB
KB_DIM = '#6E6E73'   # the action key's text while it is dimmed (the "disable" style: the Wi-Fi password page's Join before the password is valid)
KB_RADIUS = 5
KB_POP_W, KB_POP_H, KB_POP_R, KB_POP_PX, KB_POP_GAP = 46, 50, 10, 34, 10   # the balloon: 46 x 50, radius 10, its letter 34 px, 10 px above the key
KB_STEM_UP = 12                                                             # the stem rises to 12 px under the balloon's bottom edge: 22 px above the key

# The candidate strip (Chinese layer): a 36 px bar directly above the pad. At its left the pinyin being typed (16 px, grey), then a divider, then the candidates in a row that scrolls
# sideways: item widgets (labels, 20 px white) in a pool that the payload moves, each as wide as its text plus 12 px a side; a press shows a rounded highlight behind the item.
WIN_H = 450
STRIP_H, STRIP_Y = 36, WIN_H - KB_H - 36     # window coordinates: 234, so it ends where the pad begins
STRIP_BG, STRIP_PY_INK, STRIP_SEP = '#2A2A2C', '#AEAEB2', '#48484A'
PY_X, PY_MAX, PY_PX = 8, 120, 16             # the pinyin label: left margin, the room it may take, its font
CAND_PX, CAND_PAD, CAND_MIN, CAND_MAXW = 20, 12, 36, 230   # candidate font, the padding either side of its text, the narrowest and the widest item
POOL = 12                                    # candidate item widgets (kb_c0 ..): at most this many are on screen (320 / CAND_MIN rounded up, plus one)
CHL_Y, CHL_H = 4, 28                         # the pressed item's highlight
SEP_Y, SEP_H = 8, 20                         # the divider between the pinyin and the candidates
DRAG = 6                                     # px a finger must move before a press on the strip is a scroll
LANG_TAGS = ('中', 'EN')                     # the language key's label: the layer a tap goes to (Chinese from English, English from Chinese)
FR_TAG = 'FR'                                # ... and the French layer's (the cycle is EN -> FR -> 中 -> EN over the layers that are on)

# The search field (window coordinates): a rounded #1C1C1E bar under the navbar.
FIELD_X, FIELD_Y, FIELD_W, FIELD_H, FIELD_R = 10, 58, 300, 36, 10
FIELD_TEXT_X, FIELD_TEXT_W, FIELD_PX = 30, 228, 18          # the text starts 30 px into the field; room for it up to the clear button
FIELD_MAG_X, FIELD_MAG = 8, 16                               # the magnifier (16 px square)
FIELD_CLEAR_X, FIELD_CLEAR_W, FIELD_CLEAR = 264, 36, 16      # the clear button's touch area, and the 16 px disc in it
CARET_Y, CARET_W, CARET_H = 7, 2, 22
# A name entry (KB_DONE): the field on one card row (patch/keyboard.h KB_NAME_*), like Radio's Add by URL rows; kb_capsule (the search fill and magnifier) is hidden then
NAME_Y, NAME_ROW, NAME_X, NAME_DY, NAME_FIELD_W, NAME_TW = 56, 48, 24, 6, 281, 232

PAGES = ('abc', 'ABC', '123', '#+=')
ROWS = {
    'abc': ('qwertyuiop', 'asdfghjkl', 'zxcvbnm'),
    'ABC': ('QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM'),
    '123': ('1234567890', '-/:;()$&@"', ".,?!'"),
    '#+=': ('[]{}#%^*+=', '_\\|~<>€£¥`', ".,?!'"),
}
# The French layer's letter pages (AZERTY): the same 26 char key widgets (10 + 10 + 6), shift and delete as in English. Per-layer letter tables: one entry here and one in patch/keyboard.c KB_LETTERS.
FR_ROWS = {
    'abc': ('azertyuiop', 'qsdfghjklm', 'wxcvbn'),
    'ABC': ('AZERTYUIOP', 'QSDFGHJKLM', 'WXCVBN'),
}
# What the keys read: characters and the page switches, the same in every language (not translated: test/pod/i18n.py lets these literals through).
LABELS = frozenset(c for rows in ROWS.values() for row in rows for c in row) | {'#+=', '123', 'ABC'} | set(LANG_TAGS) | {FR_TAG}   # (the Chinese layer's pinyin separator ' is in the 123 page's row already)


def row_x(n, w):
    """The left edge of n keys of width w centred in the 320 px pad (rounded up)."""
    return (SCREEN_W - n * w - (n - 1) * KB_GAP + 1) // 2


def row_y(i): return KB_PAD + i * KB_PITCH


def layout(page, lang=False, zh=False, fr=False):
    """Pad-relative geometry of a page: {'keys': [(label, x, y, w)...] in char key widget order, 'fn': {name: (x, y, w)} for the function keys shown}.
    Function keys: shift (kb_shift or, while on, kb_shifton) on the letter pages, sym (#+= / 123) on the other two, del, mode (123 / ABC), space, go (Search).
    lang: the language key (kb_lang) sits right of 123 and space is that much narrower (more than one keyboard enabled). zh: the Chinese layer's letter page has no shift (no capitals are
    typed) and the pinyin separator ' (kb_sym) in its place. fr: the French layer's AZERTY letter pages (shift as in English)."""
    keys = []
    for r, row in enumerate(FR_ROWS[page] if fr and page in FR_ROWS else ROWS[page]):
        w = KB_NUM_KW if r == 2 and page in ('123', '#+=') else KB_KW
        x0 = row_x(len(row), w)
        keys += [(c, x0 + i * (w + KB_GAP), row_y(r), w) for i, c in enumerate(row)]
    letters = page in ('abc', 'ABC')
    left, right = KB_EDGE, SCREEN_W - 1 - KB_FN_W
    fn = {'sym' if zh and page == 'abc' else 'shift' if letters else 'sym': (left, row_y(2), KB_FN_W), 'del': (right, row_y(2), KB_FN_W), 'mode': (left, row_y(3), KB_MODE_W)}
    sx = left + KB_MODE_W + KB_GAP
    if lang:
        fn['lang'] = (sx, row_y(3), KB_LANG_W)
        sx += KB_LANG_W + KB_GAP
    fn['space'] = (sx, row_y(3), SCREEN_W - 1 - KB_MODE_W - KB_GAP - sx)
    fn['go'] = (SCREEN_W - 1 - KB_MODE_W, row_y(3), KB_MODE_W)
    return {'keys': keys, 'fn': fn}


def nearest_key(lay, x, y):
    """The key a touch at pad-relative (x, y) goes to, as patch/keyboard.c resolves it: ('char', index) or ('fn', role) for the key whose rectangle is nearest (the squared distance from the
    point to the rectangle; 0 inside), the first of equals in widget order (char keys, then shift / sym, del, mode, lang, space, go). Returns (kind, id, squared distance)."""
    cands = [('char', i, (cx, cy, w)) for i, (_, cx, cy, w) in enumerate(lay['keys'])] + [('fn', role, v) for role, v in lay['fn'].items()]
    best = None
    for kind, ident, (cx, cy, w) in cands:
        dx = cx - x if x < cx else x - (cx + w - 1) if x >= cx + w else 0
        dy = cy - y if y < cy else y - (cy + KB_KH - 1) if y >= cy + KB_KH else 0
        d = dx * dx + dy * dy
        if best is None or d < best[2]: best = (kind, ident, d)
    return best


def pop_rect(x, y, w, pad_y):
    """(balloon x, y, stem x, y, w, h) in window coordinates for the key at pad-relative (x, y, w): the balloon KB_POP_GAP above the key, centred on it and kept 1 px inside the
    screen; the stem as wide as the key from KB_STEM_UP under the balloon's bottom edge down over the key."""
    top = pad_y + y
    bx = min(max(x + w // 2 - KB_POP_W // 2, 1), SCREEN_W - 1 - KB_POP_W)
    by = top - KB_POP_GAP - KB_POP_H
    sy = by + KB_POP_H - KB_STEM_UP
    return bx, by, x, sy, w, top + KB_KH - sy


# Long-press accents (English and French letter pages): holding a char key for ACC_MS replaces the balloon with a strip of variants above the key; sliding picks one, lifting types it. French-first order (as iOS French).
# One table for both layers; the uppercase pages use the capitals. patch/keyboard.c KB_ACCENTS repeats it (test/pod/keyboard.py compares).
ACCENTS = {'e': 'éèêë', 'a': 'àâæáäãå', 'c': 'ç', 'u': 'ùûüú', 'i': 'îïìí', 'o': 'ôœöòóõø', 'y': 'ÿ', 'n': 'ñ'}
ACC_MS = 500                                   # how long a key is held before the strip shows
ACC_CELL, ACC_H, ACC_PAD, ACC_R, ACC_GAP, ACC_PX = 28, 44, 4, 10, 8, 24   # a variant's cell width, the strip's height, its padding, corner radius, the gap over the key, the font
ACC_HL_R = 6                                   # the highlighted variant's pill
ACC_MAX = 7                                    # variant label widgets (kb_a0 ..): the longest list (a: 7, o: 7)
KB_ACC_HL = '#3A3A3C'                          # the highlighted variant: a darker pill in the pop-up grey, the text stays white


def accents(c):
    """The variants of the letter c (any case), or '' for a key without; capitals for a capital."""
    v = ACCENTS.get(c.lower(), '')
    return v.upper() if c.isupper() else v


def acc_rect(x, w, y, n):
    """(strip x, y, w, h, reversed) in window coordinates for n variants over the key at pad-relative (x, y, w): left-aligned with the key (growing right) for keys in the left half of the screen, otherwise
    right-aligned (growing left, the variants in reverse slot order so the first stays nearest the key, as iOS does); kept 1 px inside the screen."""
    sw = n * ACC_CELL + 2 * ACC_PAD
    rev = x + w // 2 >= SCREEN_W // 2
    sx = x + w + ACC_PAD - sw if rev else x - ACC_PAD
    sx = min(max(sx, 1), SCREEN_W - 1 - sw)
    return sx, WIN_H - KB_H + y - ACC_GAP - ACC_H, sw, ACC_H, rev


def acc_pick(rect, n, fx):
    """The variant index a finger at window x fx selects on the strip rect (acc_rect's): the slot under it (clamped to the ends), reversed on a reversed strip."""
    sx, _, _, _, rev = rect
    slot = min(max((fx - sx - ACC_PAD) // ACC_CELL, 0), n - 1)
    return n - 1 - slot if rev else slot
