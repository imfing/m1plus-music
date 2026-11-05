"""Localisation: the string tables (reader / writer, our keys in all 16), our assets and payload texts going through
the stock translation, every language's payload output, widths per language, glyphs in the shipped font."""
import os, re, stat
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import build, awtk_strings, awtk_style, pod_i18n, pod_keyboard
from awtk_text import Ttf, StbText

RAW = os.path.join('rootfs', 'release', 'assets', 'default', 'raw')
SAME_AS_ENGLISH = {'Cover Flow', 'Playlists', 'Playlist', 'Genres', 'Gain', 'Extras', 'Albums', 'Artists', 'Local', '%s, %s'}   # translations that are the English word by design
SAME_AS_ENGLISH |= {'%d minute', '%d minutes'}    # French writes minute(s) as English does
SAME_AS_ENGLISH |= {'Podcasts', ', %d', 'Normal', 'Chrome', 'Metal', 'Graphite', '5 s', '10 s'}    # Podcasts in French and German
SAME_AS_ENGLISH |= {'Downloads', '%d MB', '%d.%d GB', '%d GB'}    # German writes Downloads as English does
SAME_AS_ENGLISH |= {'Genre', 'Screenshot', 'Collections', 'Cover'}    # French and German write Genre the same; German and Italian say Screenshot; French writes Collections the same; German says Cover
SAME_AS_ENGLISH |= {'Orange', 'Champagne', 'Neutral'}    # colour names: Orange in French and German, Champagne in French and Italian, Neutral in German
SAME_AS_ENGLISH |= {'Radio', 'LIVE', 'Live', '%d stations'}    # Radio in French, German, Spanish, Italian and Polish; LIVE and Live in German and Italian; "stations" in French
SAME_AS_ENGLISH |= {'A request is still running', 'Configuration is too long', 'Connect to browse your music', 'Could not load Navidrome albums', 'Could not load Navidrome artists', 'Could not load album tracks', 'Could not open login field', 'Could not prepare stream queue', 'Download failed; check card space and server permission', 'Enter URL|username|password', 'Enter a valid HTTP or HTTPS server URL', 'Enter a valid username', 'Enter a server password', 'Library sync could not start', 'Navidrome', 'Navidrome Search', 'Original song downloaded to /mnt/mmc/Navidrome', 'Password cannot contain |', 'Search could not start', 'Search songs', 'Searching Navidrome…', 'Select a song first', 'Server', 'Server URL', 'Server URL must use HTTP or HTTPS', 'Server password', 'Server settings are too long', 'Syncing library to SD card…', 'Tracks', 'Untitled', 'Username', 'Wait for the current request to finish', 'Songs', 'DSD Downloads', 'Connect to Wi-Fi before using Navidrome.', 'Connect to Wi-Fi before adding a server.', 'Connect to Wi-Fi to check Navidrome.', 'Checking Navidrome server…', 'Connected to Navidrome', 'Connected · syncing songs and artwork…', 'Could not connect. Check Wi-Fi, URL and login.', 'Sync the library after connecting to the server.', 'No DSD tracks in the synced library', 'DSD downloads · original files only', 'DSD streaming is disabled; download the original file for local playback.', 'Downloading original DSD file to SD…', 'DSD download could not start', 'Artwork cache busy. Retry DSD download when it finishes.', 'Adding downloaded DSD to the SD library…', 'DSD downloaded and added to the SD library.', 'DSD downloaded, but the SD library refresh failed.', 'Downloading original file to SD card…', 'Download could not start', 'Synced %d songs. Artwork cached when available.', 'Could not check Navidrome server.', 'Library sync failed; check Wi-Fi, server and SD space.'}  # Navidrome transport uses the English text where no stock translation exists
SAME_AS_ENGLISH |= {'Sync complete. Artwork cached when available.'}
SAME_AS_ENGLISH |= {'Syncing cover artwork to SD…'}
SAME_AS_ENGLISH |= {'Connected'}
SAME_AS_ENGLISH |= {'Sync Navidrome songs and artwork to the SD card now?', 'No regular songs in the synced library', 'Could not refresh this song page', 'Delete this downloaded DSD track from the SD card?', 'Could not delete the downloaded DSD file', 'Downloaded DSD track deleted', 'Download this DSD track first', 'Could not play the downloaded DSD file'}
SAME_AS_ENGLISH |= {'Version %s', 'Apple Podcasts', 'Wi-Fi', 'Wi-Fi MAC', 'Bluetooth', 'EQ', 'System', 'Display', 'Firmware', 'Model', 'Device', 'Status', 'Auto'}    # brand and technical words (Wi-Fi, Bluetooth, EQ); System in German and Polish, Display in Italian
SAME_AS_ENGLISH |= {'Codec', 'Bitrate', 'Source'}    # Station Info: Codec in French, German and Italian, Bitrate in German and Italian, Source in French



def call_args(src, name):
    """The text inside every `name( ... )` call of C source `src` (balanced parentheses)."""
    out = []
    for m in re.finditer(r'\b' + name + r'\(', src):
        depth, i = 1, m.end()
        while depth and i < len(src):
            depth += {'(': 1, ')': -1}.get(src[i], 0); i += 1
        out.append(src[m.end():i - 1])
    return out


def run(ctx):
    expect = ctx.expect
    stock_raw = os.path.join(paths.find_stock(paths.ZIP), RAW)
    tables_dir, stock_dir = os.path.join(WORK, RAW, 'strings'), os.path.join(stock_raw, 'strings')
    stock = {f[:-4]: awtk_strings.load(os.path.join(stock_dir, f)) for f in sorted(os.listdir(stock_dir))}
    built = {f[:-4]: awtk_strings.load(os.path.join(tables_dir, f)) for f in sorted(os.listdir(tables_dir))}
    ALL, LOC = pod_i18n.ALL_TABLES, pod_i18n.LOCALES

    # 1. The reader and writer: the 16 stock tables round-trip byte for byte; keys stay sorted and unique; text is UTF-8.
    for loc in ALL:
        data = open(os.path.join(stock_dir, loc + '.bin'), 'rb').read()
        expect(awtk_strings.serialize(awtk_strings.parse(data)) == data, f'stock {loc}.bin round-trips byte-exact')
    sample = [('a', 'x'), ('b', '日本語'), ('c', 'Привет')]
    expect(awtk_strings.parse(awtk_strings.serialize(sample)) == sample and awtk_strings.serialize([]) == bytes(12),
           'a small table with CJK and Cyrillic round-trips; an empty one is the 12 header bytes')
    for bad in ([('b', '1'), ('a', '2')], [('a', '1'), ('a', '2')]):
        try: awtk_strings.serialize(bad); ok = False
        except AssertionError: ok = True
        expect(ok, f'unsorted or duplicate keys are refused ({bad})')
    expect(sorted(stock) == ALL and len(ALL) == 16 and set(LOC) | set(pod_i18n.TWINS) == set(ALL), 'there are 16 tables: 13 the language menu reaches, 3 stubs')

    # 2. The built tables: the stock entries untouched, our keys added, in all 16, sorted for the binary search.
    for loc in ALL:
        want = pod_i18n.add_to_tables({loc: stock[loc]})[loc]
        expect(built[loc] == want, f'{loc}: the stock entries plus exactly our {len(pod_i18n.TEXT)} keys')
        have = dict(built[loc])
        keys = [k.encode() for k, _ in built[loc]]
        expect(keys == sorted(keys), f'{loc}: sorted')
        expect(all(have.get(k) for k in pod_i18n.TEXT), f'{loc}: every added key is there and not empty')
        expect(stat.S_IMODE(os.stat(os.path.join(tables_dir, loc + '.bin')).st_mode) == stat.S_IMODE(os.stat(os.path.join(stock_dir, loc + '.bin')).st_mode), f'{loc}: file mode kept')
    en = dict(built['en_US'])
    expect(all(en[k] == k for k in pod_i18n.TEXT), 'en_US: our keys are their own English text')
    for loc in LOC:
        have = dict(built[loc])
        expect(all(have.get(k) for k in pod_i18n.STOCK) and all(dict(stock['en_US'])[k] == v for k, v in pod_i18n.STOCK.items()),
               f'{loc}: the stock keys we use are there and en_US reads as pod_i18n.STOCK says')
        same = {k for k in pod_i18n.TEXT if have[k] == k}
        expect(loc == 'en_US' or same <= SAME_AS_ENGLISH, f'{loc}: only the words that stay English by design are untranslated ({sorted(same - SAME_AS_ENGLISH)})')
    for stub, twin in pod_i18n.TWINS.items():
        expect(all(dict(built[stub])[k] == dict(built[twin])[k] for k in pod_i18n.TEXT), f'{stub} holds {twin}\'s language')
    for k, by in pod_i18n.TEXT.items():
        counts = {loc: by[loc].count('%d') for loc in LOC}
        expect(set(counts.values()) == ({k.count('%d')} if k.startswith(('%d', 'Added %d')) or k.startswith('Cancelled, ') or k in pod_i18n.DATE_KEYS else {0}) and all('%' not in by[l].replace('%d', '').replace('%s', '') for l in LOC)
               and all(by[l].count('%s') == k.count('%s') for l in LOC),
               f'{k!r}: %d only in the track counts, once each; %s only in the Daily Mix templates, as often as the key has it')
    expect(sorted(pod_i18n.TEXT) == pod_i18n.KEYS and all(set(by) == set(LOC) for by in pod_i18n.TEXT.values()), 'every key has all 13 languages')

    # 3. Our assets: tr_text keys, no English left but the brand names.
    used = set()
    for page in pod_pages.PAGES:
        tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', page.key + '.bin'), 'rb').read())
        bad = []
        for w in tree.walk():
            t, k = w.get('text'), w.get('tr_text')
            if k is not None:
                used.add(k)
                if k not in pod_i18n.TEXT and k not in pod_i18n.STOCK: bad.append((w.name, k))
            if t not in (None, '') and t not in pod_i18n.BRANDS and t not in pod_keyboard.LABELS: bad.append((w.name, t))
            expect(not (t and k), f'{page.key}:{w.name} does not carry both text and tr_text')
        expect(not bad, f'{page.key}: every text is a tr_text key of ours or the stock tables, or a brand name ({bad})')
        title = tree.find('label_title')
        expect(pod_i18n.shown_english(title) == page.title, f'{page.key}: the title reads {page.title!r} (was {pod_i18n.shown_english(title)!r})')
        for i, r in enumerate(page.rows):
            lab = next(c for c in tree.find(f'pod_row{i}').children if c.type == 'hscroll_label')
            expect(pod_i18n.shown_english(lab) == r.label, f'{page.key}:pod_row{i} reads {r.label!r}')
    expect(tree is not None and used, 'the pages use keys')
    cover = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', 'm1plus_cover.bin'), 'rb').read())
    expect(cover.find('btn_cancel').get('tr_text') == 'Cancel', 'the Cancel button is translated')
    expect(pod_i18n.key_for('Settings') == 'Settings' and pod_i18n.key_for('Hi-Res') == 'hr' and pod_i18n.key_for('M1+ Music') is None
           and pod_i18n.key_for('Tidal') is None and pod_i18n.key_for('Albums') == 'Albums', 'stock keys where the English is the same, brand names plain')

    # 4. The payload's source: nothing user-visible bypasses the translation.
    sources = {f: open(os.path.join(ROOT, 'patch', f), encoding='utf-8').read() for f in sorted(os.listdir(os.path.join(ROOT, 'patch'))) if f.endswith('.c')}
    literal = re.compile(r'"((?:[^"\\]|\\.)*)"')
    keys_in_c = set(); plain = []
    for f, src in sources.items():
        for a in call_args(src, 'widget_set_text_utf8'):
            for inner in call_args(a, 'TR'): a = a.replace(inner, '')       # a translated key inside is fine
            for lit in literal.findall(a):
                if lit not in ('', 'M1+ Music', 'iTunes', 'Deezer') and lit not in pod_keyboard.LABELS: plain.append((f, lit))
        for a in call_args(src, 'toast') + call_args(src, 'pod_toast'):
            if literal.search(a) and not a.startswith('TR('): plain.append((f, a))
        for name in ('TR', 'widget_set_tr_text'):
            for a in call_args(src, name):
                keys_in_c.update(literal.findall(a))
    expect(not plain, f'no text is set or toasted untranslated: {plain}')
    expect(all(k in pod_i18n.TEXT or k in pod_i18n.STOCK for k in keys_in_c), f'every key the payload uses exists ({sorted(k for k in keys_in_c if k not in pod_i18n.TEXT and k not in pod_i18n.STOCK)})')
    orphans = set(pod_i18n.TEXT) | set(pod_i18n.STOCK)
    orphans -= used | {k for k in orphans if any(f'"{k}"' in src for src in sources.values())}
    expect(not orphans, f'every key is used by an asset or the payload: {sorted(orphans)}')
    expect({'Landscape', 'Album Order', 'Artist', 'album', 'Cover Flow'} <= used | keys_in_c and 'Cover Flow landscape' not in pod_i18n.TEXT,
           'Settings > Library uses its keys (rows in the asset, the value by key in the payload); the old landscape row key is gone')
    expect(all(k in sources['home.c'] for k in ('"M1+ Music"',)), 'the Home icon keeps the brand name as plain text')
    expect(len(re.findall(r'locale_info_tr|widget_set_tr_text', ' '.join(pod.FUNCTIONS))) == 2 and pod.FUNCTIONS['locale_info_tr'][2] == 0x658db4
           and pod.FUNCTIONS['widget_set_tr_text'][2] == 0x66f994 and pod.FUNCTIONS['locale_info'][2] == 0x6588b0, 'the three stock translation functions are pinned')

    # 5. The payload in every language (the stock lookup mocked with the built table): each text it sets is the table's.
    shuffle = sibling('shuffle')
    play = PSYMS['shuffle_play']
    cover_open = PSYMS['coverflow_open']
    open_artists = PSYMS['artists_open']
    A = offsets()
    for loc in ALL:
        T = tr_of(loc)
        text_of = lambda m, w: [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == w][-1:]
        tr_keys = lambda m, w: [c[2] for c in m.calls if c[0] == 'widget_set_tr_text' and c[1] == w]
        # Artists: the title follows the mode, the empty message
        m = artists_machine(); m.set_language(loc)
        m.call(open_artists, count=5000000)
        title = m.widgets['label_title']
        big = m.widgets['ar_title']   # both titles are the table's text (set as text through the title fit, as the Songs lists')
        expect(text_of(m, title) == [T('Artists')] and text_of(m, big) == [T('Artists')], f'{loc}: the Artists titles read {T("Artists")!r}')
        m.call(PSYMS['ar_on_toggle'], count=5000000)
        expect(text_of(m, title) == [T('Album Artists')] and text_of(m, big) == [T('Album Artists')], f'{loc}: the Album Artists titles')
        m = artists_machine(artists=()); m.set_language(loc)
        m.call(open_artists, count=2000000)
        st = m.widgets['label_status']
        expect(tr_keys(m, st) == ['Update Local Music first'] and text_of(m, st) == [T('Update Local Music first')], f'{loc}: the empty Artists message')
        # an artist without albums, and the All albums card
        m = artists_machine(); m.set_language(loc); m.call(open_artists, count=5000000)
        artists_tap(m, 2)
        st = m.widgets['label_status']
        expect(text_of(m, st) == [T('No albums')] and tr_keys(m, st) == ['No albums'], f'{loc}: an artist without albums')
        m = artists_machine(); m.set_language(loc); m.call(open_artists, count=5000000)
        artists_tap(m, 0)
        put_value(m, 3); m.call(PSYMS['on_changed'], count=2000000)
        expect(text_of(m, m.widgets['label_album']) == [T('All albums')], f'{loc}: the All albums card')
        # Cover Flow: empty library, too large, first-run status and progress
        m = cover_machine(albums=0); m.set_language(loc); m.call(cover_open, count=2000000)
        expect(text_of(m, m.widgets['label_status']) == [T('Update Local Music first')], f'{loc}: Cover Flow with no library')
        m = cover_machine(albums=4001, cached=False); m.set_language(loc); m.call(cover_open, count=50000000)
        expect(text_of(m, m.widgets['label_status']) == [T('Library too large')], f'{loc}: Cover Flow with a library over the limit')
        m = cover_machine(albums=3, cached=False); m.set_language(loc); m.call(cover_open, count=5000000)
        st = m.widgets['label_status']
        expect(text_of(m, st) == [T('Preparing covers...')] and tr_keys(m, st) == ['Preparing covers...'], f'{loc}: Cover Flow preparing')
        m.call(PSYMS['on_poll'], count=2000000)
        expect(text_of(m, st) == [T('Preparing covers...') + ' 0/3'], f'{loc}: the progress line is the translation and the count ({text_of(m, st)})')
        # Albums grid with no library
        m = Machine(); m.set_language(loc)
        for w in ('btn_return', 'btn_backtoplayer', 'btn_albumview', 'view_grid', 'albums_scrollview', 'label_status', 'label_row_title', 'label_row_sub', 'label_grid_title', 'label_grid_sub'): m.widget(w)
        m.call(PSYMS['albums_open'], count=2000000)
        expect(text_of(m, m.widgets['label_status']) == [T('Update Local Music first')], f'{loc}: the empty Albums page')
        # Shuffle: the message boxes
        def toast_of(m): return [c[1] for c in m.calls if c[0] == 'toast']
        m = shuffle.shuffle_machine([]); m.set_language(loc)
        m.call(play, a0=0, count=50000000)
        expect(toast_of(m) == [T('Update Local Music first')], f'{loc}: Shuffle with no library')
        m = shuffle.shuffle_machine([('/mnt/mmc/a/1.flac', 'A', 1)], present=False); m.set_language(loc)
        m.call(play, a0=0, count=50000000)
        expect(toast_of(m) == [T('Storage unavailable')], f'{loc}: Shuffle with the card out')
        m = shuffle.shuffle_machine([('/mnt/mmc/a/1.flac', 'A', 1), ('/mnt/mmc/b/1.flac', 'B', 1)]); m.set_language(loc); m.calloc_fail = True
        m.call(play, a0=1, count=50000000)
        expect(toast_of(m) == [T('Not enough memory')], f'{loc}: Shuffle Albums without memory')
        m = shuffle.shuffle_machine([]); m.set_language(loc)
        one = shuffle.song(m, '/mnt/mmc/big/01.flac', 'Big', 1); m.present.add('/mnt/mmc/big/01.flac')
        m.showlist = [one] * (A['SHUFFLE_MAX'] + 1)
        m.call(play, a0=1, count=50000000)
        expect(toast_of(m) == [T('Too many songs to shuffle')], f'{loc}: Shuffle Albums with too many songs')

    # 6. English stays English: no table, or a table without the key, shows the key (= the English text).
    m = artists_machine(); m.call(open_artists, count=5000000)
    expect(text_of(m, m.widgets['label_title']) == ['Artists'], 'no translation loaded: English')

    # 7. Widths in the shipped font, per language: rows, titles, messages, buttons.
    font = Ttf(os.path.join(WORK, RAW, 'fonts', 'default.ttf'))
    th = awtk_style.parse(open(os.path.join(WORK, RAW, 'styles', 'default.bin'), 'rb').read())
    px_of = lambda widget, style: th.find(widget, style, 'normal')[0].get('font_size')
    row_px, title_px, msg_px = px_of('hscroll_label', 'srlabel_leftwhite21_style'), px_of('label', 'navbar_label_white'), px_of('hscroll_label', 'srlabel_msgwhite_style')
    width = lambda text, px: StbText(font, px).layout(text)[1]
    tr_text = lambda loc, key: pod_i18n.tr(loc, key, {l: dict(built[l]) for l in LOC})
    over = []
    for page in pod_pages.PAGES:
        tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', page.key + '.bin'), 'rb').read())
        lt = tree.find('label_title')
        labels = [(i, r.label) for i, r in enumerate(page.rows) if pod_pages.row_kind(r) not in ('value', 'info')]   # a value row's label shares its room with the value: checked below
        if page.kind == 'pdcfg': labels = list(enumerate(pod_pages.PULLDOWN_TILES))   # the Control Center page's rows are the tiles, beside the up arrow
        keys = [(english, [c for c in tree.find(f'pod_row{i}').children if c.type == 'hscroll_label'][0].w) for i, english in labels]
        for loc in LOC:
            if pod_i18n.key_for(page.title) and page.kind != 'songs':   # the Songs page's small title is hidden by the payload where it does not fit (test/pod/songs.py)
                w = width(tr_text(loc, pod_i18n.key_for(page.title)), title_px)
                if w > lt.w: over.append((page.key, 'title', loc, w, lt.w))
            for english, room in keys:
                k = pod_i18n.key_for(english)
                if k and width(tr_text(loc, k), row_px) > room: over.append((page.key, english, loc, width(tr_text(loc, k), row_px), room))
    # the one accepted overflow (the user's choice): the Control Center page's Playback row in Russian (Воспроизведение, the Settings header's word) ends in an ellipsis and scrolls when focused
    cut = [o for o in over if o[:3] == (pod_pages.PULLDOWN_PAGE.key, 'Playback', 'ru_RU')]
    over = [o for o in over if o not in cut]
    expect(len(cut) == 1, f'the Russian Playback row of Control Center is the one label cut with an ellipsis ({cut})')
    expect(not over, f'every menu, Extras, Shuffle, Settings and Main Menu row and every page title fits its label in all 13 languages ({over[:40]})')
    hdr_over = []   # the section headers of the Extras and Settings > Extras pages: 16 px grey captions in labels of 274 px
    for page in (pod_pages.EXTRAS_PAGE, pod_pages.EXTRASCFG_PAGE):
        tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', page.key + '.bin'), 'rb').read())
        for g, title in enumerate(pod_pages.EXTRAS_TITLES):
            cap = tree.find(f'pod_hdr_text{g}')
            for loc in LOC:
                w = width(tr_text(loc, pod_i18n.key_for(title)), pod_ui.HDR_PX)
                if w > cap.w - 4: hdr_over.append((page.key, title, loc, w, cap.w))
    expect(not hdr_over, f'every Extras section header (Play, Library, Collections, Tools) fits its label in all 13 languages at {pod_ui.HDR_PX} px ({hdr_over[:4]})')
    albums_tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', pod_pages.ALBUMS.key + '.bin'), 'rb').read())
    albums_lbl, cf_btn = albums_tree.find('label_title'), albums_tree.find('btn_coverflow')
    over = [(loc, width(tr_text(loc, pod_i18n.key_for('Albums')), title_px)) for loc in LOC
            if albums_lbl.x + width(tr_text(loc, pod_i18n.key_for('Albums')), title_px) > cf_btn.x]
    expect(not over and albums_lbl.x + albums_lbl.w == cf_btn.x == A['NAV_CF_X'], f'the Albums title ends before the Cover Flow button (x {cf_btn.x}) in all languages, at {title_px} px ({over})')
    # the artist page's title (the artist's name, set at run time) is cut at the Songs button (NAV_VIEW_X): the page's own
    # title text, which shows until then, fits that room in every language
    cf_title = cover.find('label_title')
    over = [(loc, width(tr_text(loc, pod_i18n.key_for('Cover Flow')), title_px)) for loc in LOC
            if cf_title.x + width(tr_text(loc, pod_i18n.key_for('Cover Flow')), title_px) > A['NAV_VIEW_X']]
    expect(not over, f'the Cover Flow title ends before the artist page\'s Songs button (x {A["NAV_VIEW_X"]}) in all languages ({over})')
    over = []
    for loc in LOC:
        for key in ('Update Local Music first', 'Not enough memory', 'Storage unavailable', 'Too many songs to shuffle',
                    'Screenshot saved', 'Screenshot failed', 'No music in this folder', 'New mix when Home opens', 'Covers will rebuild on Home',
                    'Cover cache cleared', 'Covers are being made, try later', 'Track durations cleared'):
            if width(tr_text(loc, key), msg_px) > 260: over.append((loc, key))          # the message box's line is 260 px (@0x4788a0)
        for key in ('Update Local Music first', 'Library too large', 'No albums', 'Not enough memory'):
            if width(tr_text(loc, key), 20) > cover.find('label_status').w: over.append((loc, key, 'status'))
        if width(tr_text(loc, 'Preparing covers...') + ' 4000/4000', 20) > cover.find('label_status').w: over.append((loc, 'progress'))
        for key in ('Preparing covers', 'Rebuilding covers', 'Measuring tracks'):
            if width(tr_text(loc, key) + ' 4000/4000', pod_ui.HC_PX) > A['HC_W'] - 2: over.append((loc, key, 'Home progress line'))   # the Home line (patch/homecover.c): one 15 px line in a 300 px label with its 2 px margin
        if width(tr_text(loc, 'Cancel'), 20) > cover.find('btn_cancel').w - 10: over.append((loc, 'Cancel'))
        if width(tr_text(loc, 'All albums'), 22) > 288: over.append((loc, 'All albums'))
        # the pill: the text is centred in a 104 px rect (194 - margins 32 + 29 - the 44 px icon square - the spacer -15)
        if width(tr_text(loc, 'Play all'), 20) > 104: over.append((loc, 'Play all', 'pill'))
        for key in ('%d track', '%d tracks'):
            if width('1959 \xb7 ' + tr_text(loc, key).replace('%d', '9999'), 13) > A['AH_TEXT_W']: over.append((loc, key, 'count line'))
        for key in pod_pages.SORT_VALUES:                              # the Sort row's value, in its own label (and the Artist/Album words in the title room)
            k = pod_i18n.key_for(key)
            if width(tr_text(loc, k), pod_ui.VALUE_PX) > pod_ui.VALUE_W - 4: over.append((loc, key, 'sort value'))
    # The Rebuild Covers confirm: the stock dialog's wrapped label (centred white 20 px, 260 x 80 at y 25, @0x472e1c) takes at most
    # three lines. A line breaks at a space; a CJK or Thai character is a break of its own (conservative for Thai, which has none).
    wrap_px = px_of('label', 'label_centerwhite20_style')
    pads = [(t.get('margin_left'), t.get('margin_right')) for t in th.find('label', 'label_centerwhite20_style')]   # the label of the confirm dialog's kind 5 (0x472e1c) is used by that one dialog only: its margins are the padding
    expect(pads == [(12, 12)] * 3, f'the confirm dialog message label (label_centerwhite20_style) has a 12 px margin each side in all three states ({pads})')
    wrap_w = 260 - 2 * 12
    unit = re.compile(r'[^\s⺀-鿿＀-￯฀-๿]+\s*|[⺀-鿿＀-￯฀-๿]\s*|\s+')

    def wrapped(text, px, maxw):
        lines, cur = 1, ''
        for u in unit.findall(text):
            if cur and width((cur + u).rstrip(), px) > maxw: lines, cur = lines + 1, ''
            cur += u
            while width(cur.rstrip(), px) > maxw: lines, cur = lines + 1, cur[len(cur) // 2:]     # a unit wider than a line
        return lines
    for key, what in (('Rebuild all covers? This may take a few minutes.', 'Rebuild Covers'), ('Take a screenshot?', 'Screenshot'), ('Take a screenshot in:', 'Screenshot delay'),
                      ('Cancel the screenshot?', 'Cancel Screenshot'), ('Delete all cached covers? They will be made again on Home.', 'Clear Cover Cache'), ('Delete all measured track durations? They will be measured again on Home.', 'Clear Track Durations'), ('Delete folder and everything in it?', 'Delete folder'), ('Download %s (55 MB)? It replaces update.bin on the card.', 'Software Update'),
                      ('msg_bt_open', 'stock: Bluetooth is off'), ('msg_wifi_open', 'stock: Wi-Fi is off')):
        lines = {loc: wrapped((dict(built[loc]).get(key, dict(built['en_US'])[key]) if key.startswith('msg_') else tr_text(loc, key)).replace('%s', '10.0.1'), wrap_px, wrap_w) for loc in LOC}
        expect(wrap_px == 20 and max(lines.values()) <= 3, f'the {what} confirm wraps to at most 3 lines of {wrap_w} px at {wrap_px} px in all languages ({lines})')
        expect(key.startswith('msg_') or all(len(pod_i18n.TEXT[key][loc].encode()) < 0x1ff for loc in LOC), 'and fits the dialog context\'s 0x200 byte text')
    # the Settings cards (tools/pod_settings.py): a value and the row's label share the room between the glyph column and the chevron (the payload gives the value the room its text needs, at most VALUE_MAX);
    # every value text of every language fits with its label, and the headers and notes fit their 272 px labels
    import pod_settings as ST
    stock_values = {'wifi': ('On', 'Off'), 'bluetooth': ('On', 'Off'), 'playmode': ('playmode_listplay', 'playmode_repeattrack', 'playmode_shuffle', 'playmode_repeatall'),
                    'eq': ('Off', 'eq_custom1', 'eq_custom2', 'eq_custom3', 'eq_pop', 'eq_rock', 'eq_dance', 'eq_blues', 'eq_metal', 'eq_vocal', 'eq_classical', 'eq_jazz')}
    cards_over, room = [], ST.chevron_left() - ST.VALUE_GAP - ST.TEXT_X
    for page in [p for p in pod_pages.PAGES if p.kind == 'cards']:
        tree = awtk_ui.parse(open(os.path.join(WORK, RAW, 'ui', page.key + '.bin'), 'rb').read())
        for loc in LOC:
            for i, r in enumerate(page.rows):
                if pod_pages.row_kind(r) == 'info':   # an About row: the label and a realistic value (the longest each can be) share the room from the label to the right ink edge
                    sample = {pod_pages.INFO_TAG: build.about(build.TAG), pod_pages.INFO_FW: 'V2.1', pod_pages.INFO_MODEL: 'Shanling M1 Plus', pod_pages.INFO_SN: '888888888888', pod_pages.INFO_MAC: '88:88:88:88:88:88',
                              pod_pages.INFO_IP: '192.168.188.188', pod_pages.INFO_CAP: '188.88 GB', pod_pages.INFO_FREE: '188.88 GB'}.get(r.arg, '99999')   # (the Cover Cache counts: five digits)
                    samples = [sample]
                    if r.arg == pod_pages.INFO_CC_STATUS:   # every Status word, with a count after the three that have one
                        samples = [tr_text(loc, k) + (' 4000/4000' if k in ('Preparing', 'Rebuilding', 'Building', 'Measuring tracks') else '') for k in ('Idle', 'Preparing', 'Rebuilding', 'Rebuild requested', 'Clearing', 'Building', 'Measuring tracks')]
                    lk = pod_i18n.key_for(r.label)
                    for sample in samples:
                        need = width(tr_text(loc, lk) if lk else r.label, row_px) + ST.VALUE_LABEL_GAP + min(width(sample, ST.INFO_PX) + 6, ST.INFO_MAX)
                        if need > ST.RIGHT - ST.CM - ST.PAD: cards_over.append((page.key, r.label, sample, loc, need, ST.RIGHT - ST.CM - ST.PAD))
                    continue
                if r.action == pod_pages.ACT_CCLIST:   # the Cover Cache's No art / Missing: no glyph, a five digit count and the chevron
                    need = width(tr_text(loc, pod_i18n.key_for(r.label)), row_px) + ST.VALUE_LABEL_GAP + min(width('99999', ST.VALUE_PX) + 6, ST.VALUE_MAX)
                    if need > room + ST.TEXT_X - ST.CM - ST.PAD: cards_over.append((page.key, r.label, '99999', loc, need, room))
                    continue
                if pod_pages.row_kind(r) != 'value': continue
                vkeys = stock_values[pod_pages.STOCK_PAGES[r.arg][1]] if r.action == pod_pages.ACT_STOCK else ('Artist', 'album') if r.action == pod_pages.ACT_SORT else pod_pages.BG_VALUES if r.action == pod_pages.ACT_BG else pod_pages.ACCENT_VALUES if r.action == pod_pages.ACT_ACCENT else ('Normal', 'Chrome', 'Metal')
                for vk in vkeys:
                    need = width(tr_text(loc, pod_i18n.key_for(r.label)), row_px) + ST.VALUE_LABEL_GAP + min(width(tr_text(loc, vk), ST.VALUE_PX) + 6, ST.VALUE_MAX)
                    if need > room: cards_over.append((page.key, r.label, vk, loc, need, room))
            for node in tree.walk():
                if node.name.startswith(('pod_sec', 'pod_note')) and node.name.endswith('_t'):
                    px = int(node.get('style:normal:font_size'))
                    if width(tr_text(loc, pod_i18n.key_for(pod_i18n.shown_english(node))), px) > node.w - 4: cards_over.append((page.key, node.name, loc, px))
    expect(not cards_over, f'the Settings value rows (label and value), headers and notes fit in all 13 languages ({cards_over[:40]})')
    expect(not over, f'messages, the cover page, the album buttons and count line fit in all languages ({over[:4]})')

    # 8. Glyphs: every character of every text we add, and of the stock texts we reuse, has ink in the shipped font.
    probe = StbText(font, 20)
    missing = {}
    for loc in LOC:
        texts = [pod_i18n.TEXT[k][loc] for k in pod_i18n.TEXT] + [dict(built[loc])[k] for k in pod_i18n.STOCK]
        for t in texts:
            for c in t:
                if c != ' ' and probe.box(c) is None: missing.setdefault(c, loc)
    expect(not missing, f'no character is missing from the font: {[(hex(ord(c)), l) for c, l in missing.items()]}')
    chars = {c for loc in LOC for k in pod_i18n.TEXT for c in pod_i18n.TEXT[k][loc]} - {' '}
    print(f'  {len(chars)} distinct characters in our texts; the font subset needs no extension')
