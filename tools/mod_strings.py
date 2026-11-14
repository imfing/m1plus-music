#!/usr/bin/env python3
"""M1+ Music's texts in every language: our translation keys added to all 16 string tables (asset-only).

The pages we add (ui/m1plus_*.bin) and the payload show their texts through the stock translation:
`tr_text = key` in an asset, widget_set_tr_text / locale_info_tr in the payload (docs/architecture.md
"Localisation"). Stock keys are used as they are (tools/pod_i18n.py STOCK); the texts the stock tables have
no good key for are our own keys (the key is the English text), added here to strings/<lang>_<COUNTRY>.bin
in sorted position (the app finds a key by binary search). Each table keeps its other entries and its mode.
The stock texts the stock tables leave in English or in another language are translated (pod_i18n.STOCK_FIX).

Checks, all before anything is written: every table parses and round-trips; the stock keys exist in the 13
tables the language menu reaches, with the English the code says; no table has one of our keys already;
every translation is non-empty, has no control characters, and (the track counts) exactly one %d; every
character of every translation has a glyph with ink in the tree's font (the font step runs first, so this
is the shipped font).

Usage: mod_strings.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_strings, pod_i18n
from awtk_text import Ttf, StbText
from modlib import clone_workdir, write_keep_mode

from awtk_ui import RAW
FONT = RAW + '/fonts/default.ttf'
STRINGS = RAW + '/strings'


def check(ok, msg):
    if not ok: raise SystemExit(f'mod_strings: {msg}')


def table_paths(work):
    d = os.path.join(work, STRINGS)
    names = sorted(f for f in os.listdir(d) if f.endswith('.bin'))
    check([n[:-4] for n in names] == pod_i18n.ALL_TABLES, f'unexpected string tables {names}')
    return {n[:-4]: os.path.join(d, n) for n in names}


def check_texts(font):
    """Every translation: usable text, and drawable in `font` (a Ttf)."""
    probe = StbText(font, 20)
    for key, by in pod_i18n.TEXT.items():
        for loc in pod_i18n.LOCALES:
            t = by[loc]
            check(t and t == t.strip() and all(ord(c) >= 0x20 for c in t), f'{key!r} {loc}: empty or untidy text {t!r}')
            if key.startswith(('%d', 'Added %d', 'Downloading %d', 'See All (', 'Remove %d ')) or key in pod_i18n.DATE_KEYS or key.startswith('Cancelled, '):
                n = key.count('%d')   # the English text says how many: one, or two for the refresh dialog's "%d of %d" and "%d updated, %d failed"
                check(t.count('%d') == n and t.count('%s') == key.count('%s') and '%' not in t.replace('%d', '').replace('%s', ''), f'{key!r} {loc}: need exactly {n} %d (and {key.count("%s")} x %s) in {t!r}')   # ("%d deleted, %s freed": a count and a size)
            elif '%s' in key: check(t.count('%s') == key.count('%s') and '%' not in t.replace('%s', ''), f'{key!r} {loc}: need exactly {key.count("%s")} x %s in {t!r}')   # the Daily Mix card's templates
            else: check('%' not in t, f'{key!r} {loc}: unexpected % in {t!r}')
            for c in t:
                if c != ' ': check(probe.box(c) is not None, f'{key!r} {loc}: no glyph with ink for U+{ord(c):04X} {c!r} in the shipped font')


def check_coex(font, tables):
    """The shared warning: a text for each of the 13 languages, drawable in the shipped font, replacing a stock value that every reachable table has."""
    probe = StbText(font, 20)
    check(sorted(pod_i18n.COEX_TEXT) == sorted(pod_i18n.LOCALES), 'the Wi-Fi + Bluetooth warning needs a text for each of the 13 languages')
    for loc, t in pod_i18n.COEX_TEXT.items():
        check(t and t == t.strip() and '%' not in t and all(ord(c) >= 0x20 for c in t), f'warning {loc}: empty or untidy text {t!r}')
        for c in t:
            if c != ' ': check(probe.box(c) is not None, f'warning {loc}: no glyph with ink for U+{ord(c):04X} {c!r} in the shipped font')
        for k in pod_i18n.COEX_KEYS:
            check(dict(tables[loc]).get(k), f'{loc}: stock key {k!r} missing or empty')


def check_fix(font, tables):
    """The stock texts we translate (pod_i18n.STOCK_FIX): a key of the stock English table, a tidy text drawable in the shipped font, never en_US or Chinese, and not what the table has already."""
    probe = StbText(font, 20)
    for key, by in pod_i18n.STOCK_FIX.items():
        check(key in dict(tables['en_US']) and key not in pod_i18n.TEXT and key not in pod_i18n.COEX_KEYS, f'{key!r}: not a stock key to translate')
        check(by and set(by) <= set(pod_i18n.LOCALES) - {'en_US', 'zh_CN', 'zh_HK'}, f'{key!r}: tables {sorted(by)}')
        for loc, t in by.items():
            check(t and t == t.strip() and '%' not in t and all(ord(c) >= 0x20 for c in t), f'{key!r} {loc}: empty or untidy text {t!r}')
            check(dict(tables[loc]).get(key) != t, f'{key!r} {loc}: the stock table already reads {t!r}')
            for c in t:
                if c != ' ': check(probe.box(c) is not None, f'{key!r} {loc}: no glyph with ink for U+{ord(c):04X} {c!r} in the shipped font')


def apply(work):
    tables = {loc: awtk_strings.load(p) for loc, p in table_paths(work).items()}
    for loc in pod_i18n.LOCALES:
        have = dict(tables[loc])
        for k in pod_i18n.STOCK:
            check(have.get(k), f'{loc}: stock key {k!r} missing or empty')
        check(all(dict(pod_i18n.coex_tables(tables)['en_US']).get(k) == en for k, en in pod_i18n.STOCK.items()), 'a stock key no longer reads as the English in pod_i18n.STOCK')
    font = Ttf(os.path.join(work, FONT))
    check_texts(font)
    check_coex(font, tables)
    check_fix(font, tables)
    new = pod_i18n.built_tables(tables)   # (our keys, the stock texts left untranslated, and Wi-Fi and Bluetooth together: stock's two switch-on questions become one warning)
    grew = {}
    for loc, p in table_paths(work).items():
        data = awtk_strings.serialize(new[loc])
        grew[loc] = len(data) - os.path.getsize(p)
        write_keep_mode(p, data)
    print(f'strings: {len(pod_i18n.TEXT)} keys added to {len(new)} tables, +{min(grew.values())}..+{max(grew.values())} bytes each '
          f'(+{sum(grew.values())} in all); {len(pod_i18n.STOCK)} stock keys reused, {sum(len(by) for by in pod_i18n.STOCK_FIX.values())} stock texts of {len(pod_i18n.STOCK_FIX)} keys translated')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('out')
    a = ap.parse_args()
    clone_workdir(a.src, a.out)
    apply(a.out)


if __name__ == '__main__': main()
