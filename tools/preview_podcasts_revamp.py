#!/usr/bin/env python3
"""DESIGN PREVIEW ONLY (nothing here is built): the decided Apple Podcasts style revamp of the Podcasts pages (docs/modules/podcasts.md): the Show page (album-page
header, one Latest Episode pill, "... | Now Playing" capsule, bottom sheets, cells with state pills and badges) and the Shows page (cover grid, refresh line,
static Continue Listening row, Downloads row, "..." sheet). Every frame is a 320 x 480 device frame: the 30 px status bar and the 450 px window.

  preview_podcasts_revamp.py WORKDIR OUTDIR [--logo /tmp/m1plus-allin-check/logo.png] [--lang CODE]

Writes OUTDIR/podcasts-final-show.png, -shows.png, -states.png and OUTDIR/podcasts-search.png (round 3: the Search capsule, the keyboard page, the results, the preview with Subscribe, the Settings row)
and OUTDIR/podcasts-search2.png (the four capsule states, the caption marker).
(and OUTDIR/podcasts-subs.png: the Subscriptions page and OPML; OUTDIR/podcasts-downloads2.png: the Library rows of the Shows page and the Downloads page.)

WORKDIR is a built tree (work/mod-release): the font (measured with the stb model of tools/stb_raster.py: advance + 1 px a glyph), the glass navbar pieces and
the menu glass come from it and from tools/mod_icons.py (Lucide). The page tint is the album page's: tone() of the cover's average colour (mod_nowplaying.tone)
under the black gradient of mod_icons.ah_tint_alpha, the status bar darkened as bar_color does (patch/common.c pod_bar_color). Sizes follow the other previews (rows of
patch/offsets.inc, 16 px margins, the Albums grid's 144 px cells). Covers: All-In's real logo and synthetic stand-ins. Not pixel-exact AWTK.
"""
import argparse, os, re, sys
from PIL import Image, ImageChops, ImageDraw, ImageOps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview_icons as PI
import preview_songs as PS
import mod_icons as M
import mod_nowplaying as NP
import pod_show
from stb_raster import _paste

W, WIN, NAV, STAT = 320, 450, 50, 30
O = PI.offsets()


def average(im):
    return im.resize((1, 1), Image.BOX).getpixel((0, 0))


def bar_color(tone):
    """patch/common.c pod_bar_color of the page's window row 0 (the tone under the overlay's first alpha): darkened until the
    status bar's white glyphs keep 4.5:1. Returns (the bar's colour, the page's row 0 colour)."""
    row0 = tuple(v * (255 - M.ah_tint_alpha(0)) // 255 for v in tone); r, g, b = row0
    while 2126 * r * r + 7152 * g * g + 722 * b * b > O['NP_BAR_LUM_MAX']: r, g, b = r * 15 >> 4, g * 15 >> 4, b * 15 >> 4
    return (r, g, b), row0
WHITE, GREY, SEC, DIMT, REDISH = (255,) * 3, (0xAA,) * 3, (0xB8,) * 3, (0xA6,) * 3, (0xFF, 0x6B, 0x6B)
FOLD = (0x22, 0x22, 0x22)
CJK = '⺀-鿿＀-￯“”'      # characters that may break anywhere: CJK, fullwidth forms, curly quotes

# ------------------------------------------------------------------ drawing helpers


NO_START, NO_END = '，。、！？；：）”》」』…,.!?;:)', '“‘（《「『('


def rrect(im, x, y, w, h, r, rgba, ring=0):
    """An anti-aliased rounded rectangle (a ring of `ring` px when ring > 0) of rgba, alpha-composited (clipped)."""
    k = 4
    m = Image.new('L', (w * k, h * k), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=r * k, fill=255)
    if ring:
        inner = Image.new('L', (w * k, h * k), 0)
        ImageDraw.Draw(inner).rounded_rectangle((ring * k, ring * k, (w - ring) * k - 1, (h - ring) * k - 1), radius=max(0, r - ring) * k, fill=255)
        m = ImageChops.subtract(m, inner)
    m = m.resize((w, h), Image.LANCZOS)
    a = rgba[3] if len(rgba) > 3 else 255
    if a != 255: m = m.point(lambda v: v * a // 255)
    layer = Image.new('RGBA', (w, h), tuple(rgba[:3]) + (0,)); layer.putalpha(m)
    _paste(im, layer, x, y)


def hline(im, x0, x1, y, rgba=(255, 255, 255, 0x22)):
    _paste(im, Image.new('RGBA', (x1 - x0, 1), rgba), x0, y)


_ic = {}


def icon(name, px, rgb=WHITE, solid=False, flip=False):
    """A Lucide glyph px square (stroke 2 px, 1.5 px at 16 and under, as mod_icons.glyph 'small' / 'solid')."""
    k = (name, px, rgb, solid, flip)
    if k not in _ic:
        im = M.render(name, px, 'outline', 1.5 * 24 / px if px <= 16 else 2, solid)
        if flip: im = ImageOps.mirror(im)
        _ic[k] = M.tint(im, rgb) if rgb != WHITE else im
    return _ic[k]


def put_icon(im, name, cx, cy, px, rgb=WHITE, solid=False, flip=False):
    g = icon(name, px, rgb, solid, flip)
    _paste(im, g, int(cx - g.width / 2), int(cy - g.height / 2))


def ring(px, frac, rgb=WHITE, width=2):
    """A progress ring: a faint track and the arc from 12 o'clock for frac of the circle."""
    k = 8; n = px * k
    def arc(f, w):
        m = Image.new('L', (n, n), 0)
        d = ImageDraw.Draw(m)
        if f >= 1: d.ellipse((0, 0, n - 1, n - 1), outline=255, width=w * k)
        else: d.arc((0, 0, n - 1, n - 1), -90, -90 + 360 * f, fill=255, width=w * k)
        return m.resize((px, px), Image.LANCZOS)
    out = Image.new('RGBA', (px, px), rgb + (0,))
    track = arc(1, width).point(lambda v: v * 80 // 255)
    out.putalpha(ImageChops.lighter(track, arc(frac, width)))
    return out


def wrap(s, text, px, room, max_lines, tail=0):
    """Greedy word (Latin) / character (CJK) wrap into at most max_lines lines; the last one is cut with an ellipsis (leaving `tail` px) when the text goes on.
    Returns (lines, truncated)."""
    toks = re.findall(r'[%s]|[^\s%s]+\s*|\s+' % (CJK, CJK), text)
    lines = ['']
    for t in toks:
        if s.font.width((lines[-1] + t).rstrip(), px) <= room: lines[-1] += t; continue
        if lines[-1] == '' and s.font.width(t.rstrip(), px) > room:
            for ch in t:
                if s.font.width(lines[-1] + ch, px) > room: lines.append('')
                lines[-1] += ch
            continue
        lines.append(t.lstrip())
    lines = [l.rstrip() for l in lines]
    for i in range(1, len(lines)):      # simple kinsoku: closing punctuation never starts a line (it joins the line before), an opening quote never ends one
        while lines[i] and lines[i][0] in NO_START: lines[i - 1] += lines[i][0]; lines[i] = lines[i][1:]
        while lines[i - 1] and lines[i - 1][-1] in NO_END: lines[i] = lines[i - 1][-1] + lines[i]; lines[i - 1] = lines[i - 1][:-1]
    lines = [l for l in lines if l]
    if len(lines) <= max_lines: return lines, False
    rest = ' '.join(lines[max_lines - 1:]) if not re.search('[%s]' % CJK, text) else ''.join(lines[max_lines - 1:])
    return lines[:max_lines - 1] + [PS.fit(s, rest, px, room - tail)], True


# ------------------------------------------------------------------ covers


def grad(size, c0, c1):
    im = Image.new('RGB', (size, size)); d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / (size - 1); d.line((0, y, size, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(c0, c1)))
    return im


def synth_cover(s, kind, n=400):
    """A plausible podcast cover (a gradient, a motif, a title) at n px."""
    pal = {'brief': ((196, 38, 48), (112, 16, 28)), 'headlines': ((40, 92, 200), (14, 36, 110)), 'minute': ((46, 150, 96), (18, 84, 52)),
           'night': ((240, 172, 60), (204, 104, 32)), 'deep': ((124, 72, 192), (58, 30, 112)), 'tech': ((30, 150, 160), (10, 80, 100))}[kind]
    im = grad(n, *pal).convert('RGBA'); d = ImageDraw.Draw(im, 'RGBA'); k = n / 400
    def tx(x, y, t, px, rgb=WHITE, anchor='l'): s.text(im, x * k, y * k, t, int(px * k), rgb, anchor)
    if kind == 'brief':
        d.rectangle((40 * k, 60 * k, 360 * k, 66 * k), fill=(255, 255, 255, 230)); tx(40, 130, 'THE', 64); tx(40, 215, 'BRIEF', 110)
        d.rectangle((40 * k, 300 * k, 120 * k, 308 * k), fill=(255, 255, 255, 230)); tx(40, 345, 'Daily news, 10 minutes', 28, (255, 225, 225))
    elif kind == 'headlines':
        for r in (40, 80, 120, 160, 200): d.ellipse(((200 - r) * k, (180 - r) * k, (200 + r) * k, (180 + r) * k), outline=(255, 255, 255, 120), width=max(1, int(4 * k)))
        d.ellipse((180 * k, 160 * k, 220 * k, 200 * k), fill=(255, 255, 255, 255)); tx(36, 330, 'THE', 40); tx(36, 372, 'HEADLINES', 52)
    elif kind == 'minute':
        hs = [40, 90, 150, 110, 190, 130, 70, 160, 100, 50, 120, 80, 30]
        for i, h in enumerate(hs): d.rounded_rectangle(((34 + i * 26) * k, (210 - h / 2) * k, (50 + i * 26) * k, (210 + h / 2) * k), radius=8 * k, fill=(255, 255, 255, 235))
        tx(36, 340, 'MINUTE', 60); tx(36, 380, 'BRIEFING', 34, (220, 255, 235))
    elif kind == 'night':
        tx(200, 150, '夜听', 150, (40, 22, 8), 'm'); tx(200, 270, '故事会', 80, (40, 22, 8), 'm'); d.rectangle((120 * k, 330 * k, 280 * k, 336 * k), fill=(40, 22, 8, 255)); tx(200, 366, 'NIGHT STORIES', 26, (40, 22, 8), 'm')
    elif kind == 'deep':
        for i in range(-4, 12): d.line(((i * 60) * k, 0, (i * 60 + 400) * k, 400 * k), fill=(255, 255, 255, 40), width=int(14 * k))
        tx(36, 300, 'DEEP', 70); tx(36, 372, 'DIVE', 70)
    else:
        tx(200, 190, 'T', 280, WHITE, 'm'); d.ellipse((290 * k, 300 * k, 330 * k, 340 * k), fill=(255, 255, 255, 255)); tx(36, 372, 'Tech Daily', 40)
    return im.convert('RGB')


class Show:
    def __init__(self, key, title, cover, author, genre, sub, eps, local=False):
        self.key, self.title, self.cover, self.author, self.genre, self.sub, self.eps, self.local = key, title, cover, author, genre, sub, eps, local
        self.tone = NP.tone(*average(cover.resize((160, 160), Image.LANCZOS))) if cover is not None else None


def ep(date, title, desc, state, label, played=False, pct=0):
    return dict(date=date, title=title, desc=desc, state=state, label=label, played=played, pct=pct)


def make_shows(s, logo):
    allin = Image.open(logo)
    allin = Image.alpha_composite(Image.new('RGBA', allin.size, (255, 255, 255, 255)), allin.convert('RGBA')).convert('RGB').resize((400, 400), Image.LANCZOS)
    allin_eps = [
        ep('2d ago', "Trump's Tariffs, Nvidia's $5T Moment, AI Bubble Debate, Fed Rate Cut and the Government Shutdown Fallout",
           "Chamath, Jason, Sacks and Friedberg break down the week's biggest stories: the market's reaction, what the Fed's next move means for tech valuations, and why the shutdown is dragging on.",
           'card', '72m'),
        ep('Oct 10', "Amazon's Big Earnings Beat, Intel Gets a Lifeline, Apple's Services Surge",
           "The besties go through the earnings season: cloud growth, chips and a very long argument about whether AI capex is a bubble.", 'card', '66m', played=True),
        ep('5d ago', 'OpenAI Restructures, SoftBank Doubles Down, and What Comes After the GPU Gold Rush',
           "A deep dive on the new structure, who really controls the company, and what it means for the rest of the field.", 'partial', '35m left'),
        ep('6d ago', 'Intensifying Tech Selloff Drags Down Nasdaq as Bond Yields Climb',
           "Markets wobble as yields rise; the panel asks if this is a pause or a regime change for growth stocks.", 'remote', '48 MB'),
        ep('1w ago', 'Ep 214: The Real Reason Markets Moved This Quarter',
           "A look back at the quarter, what we got right, what we got wrong, and the three charts to watch.", 'dl', '42%', pct=42),
        ep('1w ago', 'Ep 213: Venture Capital Is Broken (And What Replaces It)',
           "Why the old fund model no longer works, how founders are raising differently, and what LPs want now.", 'paused', 'Paused'),
        ep('2w ago', 'Ep 212: The State of the Union, Annotated',
           "Line by line through the speech, with the numbers that were left out.", 'failed', 'Retry'),
    ]
    night_eps = [
        ep('2天前', '第128期｜为什么年轻人不再相信“努力就会有回报”？聊聊内卷、躺平与新的生活方式',
           '这一期我们邀请了三位八零后、九零后的朋友，聊聊他们眼中的努力、回报与生活的意义，以及在不确定的时代里如何找到属于自己的节奏。', 'card', '58分钟'),
        ep('10月10日', '第127期｜一个人的旅行：从成都到拉萨的318国道', '一辆车、一个背包，沿着川藏线走了二十一天，路上遇到的人和事。', 'card', '41分钟', played=True),
        ep('5天前', '第126期｜深夜食堂：那些被一碗面治愈的夜晚', '关于城市、孤独和一碗热汤面的故事，来自听众的真实来信。', 'partial', '剩余12分钟'),
        ep('6天前', '第125期｜搬家记：十年里搬了七次家，我学到了什么', '每一次搬家都是一次重新整理生活的机会。', 'remote', '36 MB'),
    ]
    def generic(topic, first):
        return [ep('2d ago', first, 'Today: %s, with the context behind it and what to watch next, in a short episode you can finish on the way to work.' % topic, 'card', '24m'),
                ep('Oct 10', 'The week in review', 'A look back at the stories of the week and the ones that mattered most.', 'card', '31m', played=True),
                ep('5d ago', 'A conversation about the long term', 'An interview with a guest who has spent twenty years on the subject.', 'partial', '35m left')]
    mk = lambda *a, **k: Show(*a, **k)
    return [
        mk('allin', 'All-In with Chamath, Jason, Sacks & Friedberg', allin, 'All-In Podcast', 'Technology', '3 new', allin_eps),
        mk('brief', 'The Brief', synth_cover(s, 'brief'), 'Newsroom Media', 'News', 'Updated today', generic('the headlines', 'Markets open lower, a deal in Brussels and the weather that will not quit')),
        mk('headlines', 'The Headlines', synth_cover(s, 'headlines'), 'Headlines Network', 'News', 'No Wi-Fi', generic('the front pages', 'Elections, earnings and everything else you missed overnight')),
        mk('minute', 'WSJ Minute Briefing', synth_cover(s, 'minute'), 'The Wall Street Journal', 'Business', 'Updated today', generic('business', 'Stocks rally, oil slips and the Fed speaks')),
        mk('night', '夜听故事会', synth_cover(s, 'night'), '夜听团队', '社会文化', '1 new', night_eps),
        mk('deep', 'Deep Dive with a Very Long Podcast Title', synth_cover(s, 'deep'), 'Deep Media', 'Society & Culture', 'Updated 2d ago', generic('culture', 'Why we collect things')),
        mk('tech', 'Tech Daily', synth_cover(s, 'tech'), 'Tech Daily', 'Technology', '2 new', generic('technology', 'A new chip, a new phone and a new argument')),
        mk('local', 'Lecture Series (from the card)', None, '', '', 'Local · 12 episodes' if FONT.width('Local · 12 episodes', 15) <= O['GRID_COVER'] else 'Local', allin_eps[:2], local=True),
    ]


def cover_img(sh, size, r):
    if sh.cover is None: return PI.rounded(PI.sample_cover(None, size), r)
    return PI.rounded(sh.cover.resize((size, size), Image.LANCZOS).convert('RGBA'), r)


# ------------------------------------------------------------------ page chrome


def bg_rgb(tone, y):
    """The window's colour on row y: black, or the tone under the album page's gradient."""
    if tone is None: return (0, 0, 0)
    a = M.ah_tint_alpha(y)
    return tuple(v * (255 - a) // 255 for v in tone)


def capsule_pieces(more):
    """The glass piece left of Now Playing (patch/podcasts.c pg_nav): the "..." (the left cap), only while Import is possible."""
    return ['pod_nav_more'] if more else []


def capsule(s, win, kind='more'):
    """The navbar's right end: '...' | Now Playing ('more'), or the round Now Playing alone ('none')."""
    names = capsule_pieces(kind.endswith('more'))
    for i, n in enumerate(names): PS.glass(s, win, n, O['NAV_VIEW_X'] - O['NAV_VIEW_W'] * (len(names) - 1 - i))
    PS.glass(s, win, 'ah_nav_play' if names else 'ah_nav_np', 260, 60)



def window(s, tone, content, scroll, title=None, band=False, top=0, caps='more'):
    """The 320 x 450 window: the page colour per row, the content (scrolled), then the navbar: the glass Back and Now Playing pieces over the content, and when `band`
    an opaque bar in the page colour with a soft fade below it (the nb_fade of the navbars on our text pages) and the small title."""
    win = Image.new('RGBA', (W, WIN)); d = ImageDraw.Draw(win)
    for y in range(WIN): d.line((0, y, W, y), fill=bg_rgb(tone, y) + (255,))
    part = content.crop((0, scroll, W, scroll + WIN - top))
    win.alpha_composite(part, (0, top))
    if band:
        for y in range(NAV + 20):
            a = 255 if y < NAV else M.nb_fade_alpha(y - NAV, 20)
            _paste(win, Image.new('RGBA', (W, 1), bg_rgb(tone, y) + (a,)), 0, y)
        s.text(win, O['NAV_TITLE_X'], 25, PS.fit(s, title, PI.title_px(s.tree), O['NAV_VIEW_X'] - O['NAV_TITLE_X'] - 4), PI.title_px(s.tree))
    PS.glass(s, win, 'ah_nav_back', 7, 44)
    capsule(s, win, caps)      # the capsule "... | Now Playing" (the Playlists page's left cap and the right cap)
    return win


def frame(s, win, tone):
    bar = bar_color(tone)[0] if tone is not None else (0, 0, 0)
    im = Image.new('RGBA', (W, STAT + WIN), bar + (255,))
    PI.status_bar(s, im, 0, bg=bar)
    im.alpha_composite(win, (0, STAT))
    return im



FONT = None     # tools/pod_show.py Font of the tree (the model's advances), set by main
IMGS = None     # tools/mod_icons.py podcast_images(): the build's own atlas, sheet glyphs and sheet glass


def sprite(x, y, w, h):
    """A piece of the build's atlas (pc_atlas: the pills' ends, the glyphs, the badge, the "...", the progress rings)."""
    return IMGS[M.PC_ATLAS].crop((x, y, x + w, y + h))


def glyph16(i): return sprite(i * O['PA_G_PX'], O['PA_G_Y'], O['PA_G_PX'], O['PA_G_PX'])


def bottom_sheet(s, fr, rows):
    """The Show page's bottom sheet as the payload makes it (patch/podcasts.c pg_sheet_rows): the window (not the status bar) dimmed, the sheet's own glass picture of that height (pc_sheet<n>) at
    the window's bottom, PM_ROW_H rows with hairlines, the 20 px glyph at x PS_SHEET_ICON_X, the 18 px label from PS_SHEET_TEXT_X, the grey value right aligned to PS_SHEET_VALUE_R (the label
    keeps its text: the value takes the room that is left). rows: (glyph image name or a Lucide name, label, value, rgb)."""
    dim = Image.new('RGBA', (W, WIN), (0, 0, 0, 0x82)); fr.alpha_composite(dim, (0, STAT))
    rh = O['PM_ROW_H']; h = rh * len(rows); top = fr.height - h
    fr.alpha_composite(IMGS['pc_sheet%d' % len(rows)], (0, top))
    for i, (g, label, value, rgb) in enumerate(rows):
        y = top + i * rh
        if i: hline(fr, 0, W, y, (255, 255, 255, 0x22))
        if g in IMGS: _paste(fr, IMGS[g], O['PS_SHEET_ICON_X'], y + (rh - 20) // 2)
        else: put_icon(fr, g, O['PS_SHEET_ICON_X'] + 10, y + rh / 2, 20, rgb)
        vw = FONT.width(value, 18) if value else 0
        room = O['PS_SHEET_VALUE_R'] - O['PS_SHEET_TEXT_X'] - (vw + O['PS_SHEET_GAP'] if vw else 0)
        s.text(fr, O['PS_SHEET_TEXT_X'], y + rh / 2, PS.fit(s, label, 18, room), 18, rgb)
        if value: s.text(fr, O['PS_SHEET_VALUE_R'], y + rh / 2, value, 18, GREY, 'r')
    return fr


SHOW_ROWS = [('pc_ic_speed', 'Playback Speed', '1.25×', WHITE), ('pod_ic_order', 'Episode Order', 'Newest First', WHITE), ('pc_ic_refresh', 'Refresh Feed', 'Updated 1h ago', WHITE), ('pc_ic_select', 'Select Episodes', '', WHITE),
             ('pc_ic_check', 'Mark All as Played', '', WHITE), ('pc_ic_unsub', 'Unsubscribe', '', REDISH)]
SHOWS_ROWS = [('pc_ic_import', 'Import from Card', '', WHITE)]      # Add Show stays out until search exists


def cell_rows(e):
    """The episode sheet: Download · size (not on the card) or Remove Download, and Mark as Played / Unplayed."""
    on_card = e['state'] in ('card', 'partial')
    first = ('pc_ic_trash', 'Remove Download', '', WHITE) if on_card else ('pc_ic_down', 'Download · ' + e['label'] if e['label'][0].isdigit() and 'MB' in e['label'] else 'Download', '', WHITE)
    return [first, ('pc_ic_undo', 'Mark as Unplayed', '', WHITE) if e['played'] else ('pc_ic_check', 'Mark as Played', '', WHITE)]


# ------------------------------------------------------------------ the Show page

ZH = {'Latest Episode': '最新一集', 'Episodes': '单集'}
DESCS = {'allin': 'Chamath, Jason, Sacks and Friedberg are the besties: four friends with a show about the markets, tech, politics and everything in between, every week.',
         'brief': 'The day\'s headlines in ten minutes: what happened, why it matters and what to watch next.', 'headlines': 'The front pages of the world, read for you every morning before the commute.',
         'minute': 'A short briefing on business, markets and the economy from the newsroom of The Wall Street Journal.', 'night': '每周一期，聊聊生活、旅行和那些值得记住的夜晚。让声音陪你度过一天的最后一段时光。',
         'deep': 'Long conversations about culture, history and the ideas that shape how we live.', 'tech': 'Everything in technology this week, in half an hour.'}


def LT(sh, key):
    """A label in the show's language (the app's own, Chinese here: the pages are translated in all 13 languages anyway)."""
    return ZH[key] if sh.key == 'night' else key


KINDS = {'card': ('play', 'PA_PLAY'), 'partial': ('resume', 'PA_RETRY'), 'remote': ('down', 'PA_ARROW'), 'paused': ('paused', 'PA_PAUSE'), 'failed': ('retry', 'PA_RETRY'), 'dl': ('ring', None)}


def pill_w(label): return pod_show.pill_width(FONT, label)


def state_pill(s, im, x, y, kind, label, pct=0):
    """A cell's state pill, from the atlas as the payload paints it (patch/podcasts.c pg_pill_paint): play-type kinds filled (PA_FILL_A), download-type kinds outlined (a 2 px ring, PA_RING_A); the
    glyph in the 10 px pad, the label 6 px after it. Returns the width."""
    k, glyph = KINDS[kind]
    w, h, filled = pill_w(label), O['PS_PILL_H'], k in ('play', 'resume')
    ax = O['PA_PILLF_X'] if filled else O['PA_PILLO_X']
    _paste(im, sprite(ax, O['PA_PILL_Y'], 15, 30), x, y); _paste(im, sprite(ax + 15, O['PA_PILL_Y'], 15, 30), x + w - 15, y)
    if filled: _paste(im, Image.new('RGBA', (w - 30, h), (255, 255, 255, O['PA_FILL_A'])), x + 15, y)
    else:
        for yy in (y, y + h - 2): _paste(im, Image.new('RGBA', (w - 30, 2), (255, 255, 255, O['PA_RING_A'])), x + 15, yy)
    gx, gy = x + O['PS_PILL_PADL'], y + (h - O['PA_G_PX']) // 2
    if k == 'ring':
        step = min(O['PA_RING_N'] - 1, pct * O['PA_RING_N'] // 100)
        _paste(im, sprite(step % O['PA_RING_COLS'] * 16, step // O['PA_RING_COLS'] * 16, 16, 16), gx, gy)
    else: _paste(im, glyph16(O[glyph]), gx, gy)
    s.text(im, x + O['PS_PILL_PADL'] + O['PA_G_PX'] + O['PS_PILL_GAP'], y + h / 2, label, 16, WHITE)
    return w


def latest_pill(s, im, y, label, white=True):
    """The Latest Episode pill (patch/podcasts.c pg_latest_paint): white with the dark play glyph, or outlined."""
    o = O
    w, h = pod_show.latest_width(FONT, label, white), o['PS_LATEST_H']; x = (W - w) // 2
    ax = o['PA_PILLW_X'] if white else o['PA_PILLR_X']
    _paste(im, sprite(ax, o['PA_PILL_Y'], 20, 40), x, y); _paste(im, sprite(ax + 20, o['PA_PILL_Y'], 20, 40), x + w - 20, y)
    if white: _paste(im, Image.new('RGBA', (w - 40, h), WHITE + (255,)), x + 20, y)
    else:
        for yy in (y, y + h - 2): _paste(im, Image.new('RGBA', (w - 40, 2), (255, 255, 255, o['PA_RING_A'])), x + 20, yy)
    _paste(im, glyph16(o['PA_PLAYK'] if white else o['PA_ARROW']), x + o['PS_LATEST_PADL'] - (16 - o['PS_LATEST_GLYPH']) // 2, y + (h - 16) // 2)
    s.text(im, x + o['PS_LATEST_PADL'] + o['PS_LATEST_GLYPH'] + o['PS_LATEST_GAPG'], y + h / 2, pod_show.latest_label(FONT, label, white), 18, (0, 0, 0) if white else WHITE)


def dl_badge():
    """The date line's "on the card" mark: the atlas' 12 px light grey disc with the arrow-down cut out of it."""
    return sprite(O['PA_BADGE_X'], O['PA_DOTS_Y'], O['PA_BADGE_PX'], O['PA_BADGE_PX'])


def draw_cells(s, im, y, eps, info, preview=False):
    """The episode cells from window row y, each PS_CELL_H high (patch/podcasts.c pg_paint_eps): the date line (a check when played, the disc when on the card), the title (two lines at most), the
    description (two), the state pill and the "...", a hairline under it."""
    o = O
    for e in eps:
        y0 = y; x = o['PS_CELL_X']; cy = y0 + o['PS_DATE_Y'] + o['PS_DATE_H'] // 2
        if e['played']: _paste(im, glyph16(o['PA_CHECK']), x - 1, cy - 8); x += o['PS_BADGE_CHECK_W']
        if e['state'] in ('card', 'partial'): _paste(im, dl_badge(), x, cy - o['PA_BADGE_PX'] // 2); x += o['PS_BADGE_DISC_W']
        s.text(im, x, cy, e['date'], 15, GREY)
        tl, dl = pod_show.cell(FONT, e['title'], e['desc'])
        for k, l in enumerate(tl): s.text(im, o['PS_CELL_X'], y0 + o['PS_TITLE_Y'] + k * o['PS_TITLE_PITCH'] + o['PS_TITLE_PITCH'] // 2, l, 20, DIMT if e['played'] else WHITE)
        for k, l in enumerate(dl): s.text(im, o['PS_CELL_X'], y0 + o['PS_CDESC_Y'] + k * o['PS_CDESC_PITCH'] + o['PS_CDESC_PITCH'] // 2, l, 16, GREY)
        dy = y0 + o['PS_PILL_Y'] + o['PS_PILL_H'] // 2
        if not preview:     # (the preview's episodes carry no pill and no "...")
            state_pill(s, im, o['PS_CELL_X'], y0 + o['PS_PILL_Y'], e['state'], e['label'], e.get('pct', 0))
            _paste(im, sprite(0, o['PA_DOTS_Y'], o['PA_DOTS_PX'], o['PA_DOTS_PX']), o['PS_DOTS_CX'] - o['PA_DOTS_PX'] // 2, dy - o['PA_DOTS_PX'] // 2)
        info['dots'].append((o['PS_DOTS_CX'], dy))
        y += o['PS_PCELL_H'] if preview else o['PS_CELL_H']     # (the preview's cells end under the description: PS_PCELL_H)
        hline(im, o['PS_CELL_X'], W, y - 1)
        info['cells'].append((y0, y))
    return y


def subscribe_pill(s, im, y, label='Subscribe', white=True):
    """The preview's pill (patch/podcasts.c pg_sub_pill, pg_latest_paint): Subscribe white with a dark label; no glyph, the label centred, at least PQ_SUB_MIN wide."""
    o = O
    w, tx = pod_show.subscribe_pill(FONT, label); h = o['PS_LATEST_H']; x = (W - w) // 2
    ax = o['PA_PILLW_X'] if white else o['PA_PILLR_X']
    _paste(im, sprite(ax, o['PA_PILL_Y'], 20, 40), x, y); _paste(im, sprite(ax + 20, o['PA_PILL_Y'], 20, 40), x + w - 20, y)
    if white: _paste(im, Image.new('RGBA', (w - 40, h), WHITE + (255,)), x + 20, y)
    else:
        for yy in (y, y + h - 2): _paste(im, Image.new('RGBA', (w - 40, 2), (255, 255, 255, o['PA_RING_A'])), x + 20, yy)
    s.text(im, x + tx, y + h / 2, label, 18, (0, 0, 0) if white else WHITE)


def build_show(s, sh, preview=False):
    """The Show page's content (transparent; window x, window rows: the list starts at row 50, as PG_LIST_Y). The header's blocks and their wrapped lines are tools/pod_show.py's, the same model the
    tests check the payload against: the 160 px cover (10 px corners) flush with the list, the name 14 px under it (22 px white, centred, two lines at most), the Latest Episode pill, the show's
    description (two grey lines, no MORE), the "Category · Author" line, the Episodes header, the cells."""
    o, top = O, O['PG_LIST_Y']
    im = Image.new('RGBA', (W, 3600), (0, 0, 0, 0)); info = {'dots': [], 'cells': []}
    h = pod_show.header(FONT, sh.title, DESCS.get(sh.key, ''), sh.genre, sh.author, True)
    im.alpha_composite(cover_img(sh, o['PS_ART'], o['PS_ART_R']), (o['PS_ART_X'], top))
    for k, l in enumerate(h['name']): s.text(im, 160, top + h['y_name'] + k * o['PS_NAME_PITCH'] + o['PS_NAME_PITCH'] // 2, l, o['PS_NAME_PX'], WHITE, 'm')
    local = sh.eps[0]['state'] in ('card', 'partial')
    if preview: subscribe_pill(s, im, top + h['y_latest'], 'Subscribe', True)
    else: latest_pill(s, im, top + h['y_latest'], LT(sh, 'Latest Episode') if local else 'Latest Episode · ' + sh.eps[0]['label'], local)
    for k, l in enumerate(h['desc']): s.text(im, o['PS_DESC_X'], top + h['y_desc'] + k * o['PS_DESC_PITCH'] + o['PS_DESC_PITCH'] // 2, l, 16, SEC)
    for l in h['meta']: s.text(im, o['PS_DESC_X'], top + h['y_meta'] + o['PS_META_PITCH'] // 2, l, 15, GREY)
    s.text(im, o['PS_DESC_X'], top + h['y_head'] + (o['PS_HEAD_H'] - 6) // 2, LT(sh, 'Episodes'), 22, WHITE)
    info['collapse'] = top + h['collapse']; info['episodes_y'] = top + h['y_head']; info['header'] = h
    y = draw_cells(s, im, top + h['h'], sh.eps, info, preview)
    info['end'] = y + 20   # the air under the last cell (PG_BOTTOM)
    return im.crop((0, 0, W, y + 20)), info


def show_frame(s, sh, scroll=0, sheet=None, preview=False):
    content, info = build_show(s, sh, preview)
    scroll = min(scroll, max(0, info['end'] - WIN))
    win = window(s, sh.tone, content, scroll, sh.title, scroll >= info['collapse'] - O['PG_LIST_Y'], caps='none' if preview else 'more')
    fr = frame(s, win, sh.tone)
    if sheet: bottom_sheet(s, fr, sheet)
    return fr, info


def pill_strip(s, tone):
    """The pill states at 1:1 and zoomed 2x on the page's colour (the build's own sprites)."""
    states = [('card', '58m', 'downloaded (filled)'), ('partial', '35m left', 'partly played (filled)'), ('remote', '48 MB', 'not downloaded (outline)'),
              ('remote', 'Download', 'size unknown'), ('dl', '42%', 'downloading'), ('paused', 'Paused', 'paused'), ('failed', 'Retry', 'failed')]
    bg = bg_rgb(tone, 330)
    out = Image.new('RGB', (1340, 330), bg); d = ImageDraw.Draw(out)
    d.text((12, 6), 'Cell pill states, 1:1 (top) and 2x. Play-type pills are filled, download-type pills are outlined. The ring is 12 steps of the atlas (pc_atlas); every download symbol is the Lucide arrow-down.',
           fill=(0xAA,) * 3, font=PI.ANN)
    x1 = 24; x2 = [24, 24]
    for i, (kind, label, cap) in enumerate(states):
        t = Image.new('RGBA', (pill_w(label) + 4, 34), (0, 0, 0, 0)); state_pill(s, t, 2, 2, kind, label, 42)
        base = Image.new('RGBA', t.size, bg + (255,)); base.alpha_composite(t)
        out.paste(base.convert('RGB'), (x1, 36)); d.text((x1, 74), cap, fill=(0xAA,) * 3, font=PI.ANN); x1 += 188
        z = base.resize((base.width * 2, base.height * 2), Image.NEAREST); row = i // 4
        out.paste(z.convert('RGB'), (x2[row], 110 + row * 100)); d.text((x2[row], 110 + row * 100 + 70), cap, fill=(0xAA,) * 3, font=PI.ANN); x2[row] += z.width + 36
    return out


def combos(s, sh):
    """A column of cells covering the badge combinations, on the page's tint, with a caption column to its right."""
    caps = ['unplayed, not downloaded\n(no badge; "Download" pill)', 'downloaded, unplayed\n(disc badge; filled play pill)', 'played and downloaded\n(check + disc badge; grey title)',
            'partly played (disc badge;\nfilled "35m left")', 'downloading (no badge; ring)', 'paused download', 'failed download (Retry)']
    e = sh.eps; eps = [dict(e[3]), e[0], e[1], e[2], e[4], e[5], e[6]]
    im = Image.new('RGBA', (W, 2000), (0, 0, 0, 0)); info = {'dots': [], 'cells': []}
    y = draw_cells(s, im, 8, eps, info); im = im.crop((0, 0, W, y + 8))
    col = Image.new('RGBA', im.size)
    d = ImageDraw.Draw(col)
    for yy in range(im.height): d.line((0, yy, W, yy), fill=bg_rgb(sh.tone, 330) + (255,))
    col.alpha_composite(im)
    sheet = Image.new('RGB', (W + 250, im.height), (0x2A,) * 3); sheet.paste(col.convert('RGB'), (0, 0)); d = ImageDraw.Draw(sheet)
    for (y0, _), cap in zip(info['cells'], caps):
        for k, line in enumerate(cap.split('\n')): d.text((W + 12, y0 + 12 + k * 16), line, fill=(0xAA,) * 3, font=PI.ANN)
    return sheet


# ------------------------------------------------------------------ the Shows page


def build_shows(s, shows, shelf_n, dl, refreshing):
    """The Shows page's content (window x, content y from the navbar's bottom; black), laid out by tools/pod_show.py shows_layout and drawn with the PP_* numbers of patch/offsets.inc as
    patch/podcasts.c pg_paint_home does: the large title, the refresh line (when a show has a feed), the Library rows (Downloads always, its grey line dl; Subscriptions while a show has a feed: the atlas' tile
    and the podcast tile, a chevron, a hairline), Continue Listening (a static row of at most PP_SHELF_MAX covers, only when something is partly played), the "Shows" header and the Albums grid (no badge on the covers)."""
    o = O
    shelf = [(shows[0], 'The Real Reason Markets Moved', '35m left'), (shows[4], '第126期｜深夜食堂', '12m left'), (shows[1], 'Markets open lower', '48m left')][:shelf_n]
    has_line = any(sh.key != 'local' for sh in shows)
    L = pod_show.shows_layout(len(shows), has_line, len(shelf))
    im = Image.new('RGBA', (W, L['h']), (0, 0, 0, 255)); info = dict(layout=L)
    s.text(im, o['SG_TITLE_X'], o['PP_TITLE_H'] / 2, 'Podcasts', o['PP_TITLE_PX'], WHITE)
    if has_line:
        cy = o['PP_LINE_Y'] + o['PP_LINE_H'] / 2
        if refreshing: s.text(im, o['PP_LINE_X'], cy, 'Refreshing 2/5…', 15, GREY)
        else:
            t1 = 'Updated 1h ago · '; s.text(im, o['PP_LINE_X'], cy, t1, 15, GREY); s.text(im, o['PP_LINE_X'] + FONT.width(t1, 15), cy, 'Refresh', 15, WHITE)
    if shelf:
        s.text(im, o['PP_HEAD_X'], L['y_shelf'] + o['PP_HEAD_H'] / 2, 'Continue Listening', 20, WHITE)
        for i, (sh, t, left) in enumerate(shelf):
            x, y, ty, ly = pod_show.shelf_item(i, L['y_shelf'])
            _paste(im, cover_img(sh, o['PP_SHELF_ART'], o['PP_SHELF_R']), x, y)
            _paste(im, sprite(o['PA_PLAYB_X'], o['PA_PLAYB_Y'], o['PA_PLAYB_PX'], o['PA_PLAYB_PX']), *pod_show.shelf_play(i, L['y_shelf']))
            s.text(im, x, ty + o['PP_SHELF_TITLE_H'] / 2, PS.fit(s, t, 14, o['PP_SHELF_W']), 14, WHITE)
            s.text(im, x, ly + o['PP_SHELF_LEFT_H'] / 2, left, 13, GREY)
    n_subs = sum(1 for sh in shows if sh.key != 'local')
    for y, name, sub, tile in ((L['y_srch'], 'Discover', 'Apple Podcasts', IMGS[M.PC_SRCH_TILE]),
                               (L['y_dl'], 'Downloads', dl, IMGS[M.PC_DL_TILE]),
                               (L['y_sub'], 'Subscriptions', '%d shows' % n_subs, IMGS[M.PC_LIB_TILE])):
        if not y: continue
        _paste(im, tile, o['PP_DL_TILE_X'], y + o['PP_DL_TILE_Y'])
        s.text(im, o['PP_DL_TEXT_X'], y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, name, 21, WHITE)
        s.text(im, o['PP_DL_TEXT_X'], y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, PS.fit(s, sub, 18, o['PP_DL_TEXT_W']), 18, GREY)
        _paste(im, M.pod_chevron(M.CARD_CHEVRON[3]), o['PP_DL_CHEV_X'], y + (o['PC_ROW_H'] - 1 - M.POD_CHEV_H) // 2)
        hline(im, o['PP_DL_TEXT_X'], W, y + o['PC_ROW_H'] - 1, FOLD + (255,))
    s.text(im, o['PP_SHOWS_X'], L['y_shows'] + o['PP_HEAD_H'] / 2, 'Shows', 20, WHITE)
    for a, sh in enumerate(shows):
        x, y, ty, sy = pod_show.grid_cell(a, L['y_grid'])
        _paste(im, cover_img(sh, o['GRID_COVER'], o['GRID_R']), x, y)
        s.text(im, x, ty + o['GRID_TITLE_H'] / 2, PS.fit(s, sh.title, 18, o['GRID_COVER']), 18, WHITE)
        s.text(im, x, sy + o['GRID_SUB_H'] / 2, PS.fit(s, sh.sub, 15, o['GRID_COVER']), 15, GREY)
    info['end'] = L['h']
    return im, info


def shows_frame(s, shows, shelf_n=3, dl='12 episodes · 1.4 GB', scroll=0, refreshing=False, sheet=None, end=False, caps='none'):
    content, info = build_shows(s, shows, shelf_n, dl, refreshing)
    if end: scroll = max(0, info['end'] - (WIN - NAV))
    win = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    win.alpha_composite(content.crop((0, scroll, W, scroll + WIN - NAV)), (0, NAV))
    if scroll:
        for y in range(20): _paste(win, Image.new('RGBA', (W, 1), (0, 0, 0, M.nb_fade_alpha(y, 20))), 0, NAV + y)
    ImageDraw.Draw(win).rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0, 255))
    if scroll > O['SG_COLLAPSE']:
        n = len(capsule_pieces(caps.endswith('more')))
        s.text(win, O['NAV_TITLE_X'], 25, PS.fit(s, 'Podcasts', PI.title_px(s.tree), O['NAV_VIEW_X'] - O['NAV_VIEW_W'] * (n - 1) - O['NAV_TITLE_X']), PI.title_px(s.tree))
    PS.glass(s, win, 'ah_nav_back', 7, 44); capsule(s, win, caps)
    fr = frame(s, win, None)
    if sheet: bottom_sheet(s, fr, sheet)
    return fr, info


def search_page(s, shows, results, text='all in', hint=None, status=None):
    """The search level as patch/podcasts.c paints it (docs/modules/podcasts.md "Search"): the field at PQ_FIELD_* under the navbar (the keyboard page's field look: #1C1C1E, the magnifier, the white text or the grey hint),
    the result rows from PQ_TOP (the Downloads rows' geometry: a LIST_ART px cover, the name 21 px, the author 18 px grey, a hairline), a result with no feed dimmed (PQ_DIM) with "Not available", or the status line
    (Searching..., No results, a failure) 90 px high with its text centred. results: (name, author, show for the cover, has a feed)."""
    o = O
    win = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    fx, fy = o['PQ_FIELD_X'], NAV + o['PQ_FIELD_Y']
    rrect(win, fx, fy, o['PQ_FIELD_W'], o['PQ_FIELD_H'], o['PQ_FIELD_R'], (0x1C, 0x1C, 0x1E, 255))
    _paste(win, s.img('qk_mag'), fx + o['PQ_MAG_X'], fy + (o['PQ_FIELD_H'] - o['PQ_MAG']) // 2)
    shown = PS.fit(s, text, 18, o['PQ_TEXT_W']) if text else hint
    s.text(win, fx + o['PQ_TEXT_X'], fy + o['PQ_FIELD_H'] / 2, shown, 18, WHITE if text else (0x8E, 0x8E, 0x93))
    if text: _paste(win, s.img('qk_clear'), fx + o['PQ_CLEAR_X'] + (o['PQ_CLEAR_W'] - o['PQ_CLEAR']) // 2, fy + (o['PQ_FIELD_H'] - o['PQ_CLEAR']) // 2)     # the keyboard page's clear disc, shown with a text
    for i, (name, author, sh, feed) in enumerate(results):
        y = NAV + o['PQ_TOP'] + i * o['PC_ROW_H']
        if y + o['PC_ROW_H'] > WIN: break
        _paste(win, cover_img(sh, o['LIST_ART'], o['LIST_R']), o['LIST_ART_X'], y + o['LIST_ART_Y'])
        s.text(win, o['LIST_TEXT_X'], y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, PS.fit(s, name, 21, o['LIST_TEXT_W']), 21, WHITE)
        s.text(win, o['LIST_TEXT_X'], y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, PS.fit(s, author if feed else 'Not available', 18, o['LIST_TEXT_W']), 18, GREY)
        hline(win, 0, W, y + o['PC_ROW_H'] - 1)
        if not feed: _paste(win, Image.new('RGBA', (W, o['PC_ROW_H'] - 1), (0, 0, 0, o['PQ_DIM'] >> 24)), 0, y)
    if status: s.text(win, W // 2, NAV + o['PQ_TOP'] + 8 + 45, status, 18, WHITE, 'm')
    ImageDraw.Draw(win).rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0, 255))
    PS.glass(s, win, 'ah_nav_back', 7, 44); PS.glass(s, win, 'ah_nav_np', 260, 60)
    return frame(s, win, None)


def field_panel(s, shows):
    """The search field with and without the clear button, one above the other (the magnifier is at the same pixels in both), the field of the keyboard page under them, and the clear button zoomed 12 x (its x
    centred in the disc, measured by test/pod/pcsearchui.py field_tests)."""
    o = O
    fx, fy = o['PQ_FIELD_X'], NAV + o['PQ_FIELD_Y']
    a, b = search_page(s, shows, [], '', hint='Search'), search_page(s, shows, [], 'all in')
    out = Image.new('RGBA', (W, STAT + WIN), (0, 0, 0, 255)); d = ImageDraw.Draw(out)
    box = (0, STAT + NAV, W, STAT + NAV + o['PQ_FIELD_Y'] * 2 + o['PQ_FIELD_H'])
    d.text((10, 8), 'empty: no clear button', fill=(0xAA,) * 3, font=PI.ANN); out.paste(a.crop(box), (0, 24))
    d.text((10, 90), 'with a text: the clear button', fill=(0xAA,) * 3, font=PI.ANN); out.paste(b.crop(box), (0, 106))
    mag = (fx + o['PQ_MAG_X'] - 2, STAT + fy + 8, fx + o['PQ_MAG_X'] + o['PQ_MAG'] + 2, STAT + fy + o['PQ_FIELD_H'] - 8)
    d.text((10, 172), 'the magnifier, both states, 6 x:', fill=(0xAA,) * 3, font=PI.ANN)
    for i, src in enumerate((a, b)): out.paste(src.crop(mag).resize(((mag[2] - mag[0]) * 6, (mag[3] - mag[1]) * 6), Image.NEAREST), (10 + i * 160, 190))
    cl = (fx + o['PQ_CLEAR_X'] + 10 - 4, STAT + fy + 10 - 4, fx + o['PQ_CLEAR_X'] + 10 + 20, STAT + fy + 10 + 20)
    d.text((10, 330), 'the clear button, 5 x:', fill=(0xAA,) * 3, font=PI.ANN); out.paste(b.crop(cl).resize(((cl[2] - cl[0]) * 5, (cl[3] - cl[1]) * 5), Image.NEAREST), (10, 346))
    return out


def search_sheet(s, shows, workdir, path):
    """podcasts-search.png: the Shows page's Search capsule (both shapes), the keyboard page the field opens, the results (one with no feed), the preview with Subscribe (and Subscribed), the Settings row."""
    import json
    import preview_keyboard as PK2
    import preview_settings as PSET
    fx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'test', 'data', 'search', 'all_in_us.json'), encoding='utf-8'))['results']
    res = [(r['collectionName'], r['artistName'], shows[i % len(shows)], bool(r.get('feedUrl'))) for i, r in enumerate(fx)]
    res[2] = (res[2][0], res[2][1], res[2][2], False)
    mini = shows[3]
    prev = Show(mini.key, mini.title, mini.cover, mini.author, mini.genre, mini.sub,
                [ep(e['date'], e['title'], e['desc'], 'remote', '48 MB') for e in mini.eps], False)
    pg = PK2.Page(s)
    lib = PSET.draw_page(s, 'm1plus_library', full=True).convert('RGBA')
    lib = lib.crop((0, lib.height - (STAT + WIN), W, lib.height)) if lib.height > STAT + WIN else lib
    libf = Image.new('RGBA', (W, STAT + WIN), (0, 0, 0, 255)); PI.status_bar(s, libf, 0, bg=(0, 0, 0)); libf.alpha_composite(lib, (0, STAT + WIN - lib.height))
    frames = [('Shows page, Import possible:\n... | Now Playing', shows_frame(s, shows, shelf_n=0, caps='more')[0]),
              ('... nothing to import: the plain Now Playing disc', shows_frame(s, shows, shelf_n=0, caps='none')[0]),
              ('Search: the field opens our keyboard page', PK2.screen(s, pg, 'all in', 'abc', held='n', hint='Search')),
              ('Results: the show, its author in grey,\none with no feed: Not available, dimmed', search_page(s, shows, res[:6])),
              ('Searching...', search_page(s, shows, [], 'all in', status='Searching…')),
              ('A failure, in the existing words', search_page(s, shows, [], 'all in', status="Can't connect")),
              ('A show in the store: the preview.\nSubscribe is the Latest Episode pill', show_frame(s, prev, 0, preview=True)[0]),
              ('The preview scrolled: normal cells without\nthe pill row (shorter), no "..."', show_frame(s, prev, 330, preview=True)[0]),
              ('After Subscribe: the real Show page in place\n(pills, "...", sheets; Back = the results)', show_frame(s, prev, 0)[0]),
              ('A result that is a show already: its real page\n(cells with pills, "..."), no Subscribed', show_frame(s, mini, 0)[0]),
              ('The search field, with and without the clear\nbutton, the magnifier unmoved; clear button zoomed', field_panel(s, shows)),
              ('Settings > Library > Podcasts: Podcast Region', libf)]
    assemble(frames, 4, path)


# ------------------------------------------------------------------ the episode page (round 4): patch/podcasts.c pg_paint_det, patch/pcdetail.c; the layout is tools/pod_show.py detail_layout

NOTE_EN = '\n'.join([
    "Chamath, Jason, Sacks and Friedberg break down the week's biggest stories: the market's reaction to the Fed, what the next move means for tech valuations, and why the shutdown is dragging on.",
    'Topics: 0:00 intro; 4:10 Nvidia hits five trillion; 22:45 the AI bubble debate; 41:30 tariffs and the supreme court; 58:00 closing thoughts and what we are watching next week in the markets.',
    'Follow the besties on social media, subscribe to the newsletter and send us your questions for the next episode. Thank you for listening, and see you next week.',
    'Sponsors: this episode is brought to you by the people who make the tools we use every day. Visit the links in the show notes to support the show and to get a discount.'])
NOTE_ZH = '\n'.join([
    '本期节目中，几位主持人讨论了本周最重要的新闻：市场对美联储降息的反应、科技股估值的变化，以及政府停摆为何迟迟没有结束。他们还谈到了关税、人工智能泡沫和英伟达的五万亿美元时刻。',
    '时间线：0:00 开场；4:10 英伟达市值突破五万亿美元（这是一个历史性的时刻）；22:45 人工智能泡沫之争；41:30 关税与最高法院；58:00 结语。',
    '欢迎在社交媒体上关注我们，订阅新闻简报，并把您的问题发给我们！“谢谢收听”，下周再见。',
    '本节目由生活中常用的工具赞助。请访问节目说明中的链接支持我们，并获得优惠。'])
NOTE_WSJ = '\n'.join([
    'Hosted by Sing Lee. Stocks rally on hopes for a rate cut, oil slips for a third day and the dollar steadies ahead of the jobs report.',
    'Plus: what the latest earnings tell us about the consumer, and why retailers are betting on a late holiday surge.'])


def detail_frame(s, sh, e, note, length, scroll=0, preview=False, sheet=None):
    """The episode page (Apple Podcasts' layout, plain black): the date line with the cell's badges and the size, the title, the show row (a small cover, the name, a chevron), the cell's pill and "...", the full
    description; scrolled as a whole, the navbar's fade black."""
    o, top, P = O, O['PG_LIST_Y'], pod_show.PD
    L = pod_show.detail_layout(FONT, e['title'], sh.title, note, has_pill=not preview)
    im = Image.new('RGBA', (W, top + L['h'] + 8), (0, 0, 0, 0))
    x = P['PD_X']; cy = top + L['y_date'] + P['PD_DATE_H'] // 2
    if e['played']: _paste(im, glyph16(o['PA_CHECK']), x - 1, cy - 8); x += o['PS_BADGE_CHECK_W']
    if e['state'] in ('card', 'partial'): _paste(im, dl_badge(), x, cy - o['PA_BADGE_PX'] // 2); x += o['PS_BADGE_DISC_W']
    s.text(im, x, cy, pod_show.detail_date(e['date'], length), 15, GREY)
    for k, l in enumerate(L['title']): s.text(im, P['PD_X'], top + L['y_title'] + k * P['PD_TITLE_PITCH'] + P['PD_TITLE_PITCH'] // 2, l, 22, WHITE)
    ry = top + L['y_show']
    im.alpha_composite(cover_img(sh, P['PD_COVER'], P['PD_COVER_R']), (P['PD_X'], ry + (P['PD_SHOW_H'] - P['PD_COVER']) // 2))
    s.text(im, P['PD_SHOW_TEXT_X'], ry + P['PD_SHOW_H'] // 2, L['show'], 15, GREY)
    if L['y_pill']: _paste(im, M.pod_chevron(M.CARD_CHEVRON[3]), P['PD_CHEV_X'], ry + (P['PD_SHOW_H'] - M.POD_CHEV_H) // 2)
    if L['y_pill']:
        y0 = top + L['y_pill']
        state_pill(s, im, pod_show.PD['PD_X'], y0, e['state'], e['label'], e.get('pct', 0))
        _paste(im, sprite(0, o['PA_DOTS_Y'], o['PA_DOTS_PX'], o['PA_DOTS_PX']), o['PS_DOTS_CX'] - o['PA_DOTS_PX'] // 2, y0 + o['PS_PILL_H'] // 2 - o['PA_DOTS_PX'] // 2)
    for t, y in L['desc']: s.text(im, pod_show.PD['PD_X'], top + y + pod_show.PD['PD_PITCH'] // 2, t, 15 if L['hint'] else 16, GREY if L['hint'] else SEC)
    scroll = min(scroll, max(0, L['h'] - WIN))
    win = window(s, None, im, scroll, '', scroll > 0, caps='none')
    fr = frame(s, win, None)
    if sheet: bottom_sheet(s, fr, sheet)
    return fr


def detail_sheet(s, shows, path):
    allin, night, minute = shows[0], shows[4], shows[3]
    en, zh, wsj = allin.eps[0], night.eps[0], minute.eps[0]
    remote = allin.eps[3]
    frames = [('Episode page: a downloaded episode, long English\ndescription (scrollable), pill and "..." as the cell', detail_frame(s, allin, en, NOTE_EN, 48 << 20)),
              ('the same, scrolled: the page scrolls as a whole,\nthe navbar fades in black', detail_frame(s, allin, en, NOTE_EN, 48 << 20, 330)),
              ('... scrolled to the end', detail_frame(s, allin, en, NOTE_EN, 48 << 20, 5000)),
              ('a Chinese show: long Chinese description,\nwrapped between characters (kinsoku)', detail_frame(s, night, zh, NOTE_ZH, 36 << 20)),
              ('Chinese, scrolled', detail_frame(s, night, zh, NOTE_ZH, 36 << 20, 330)),
              ('not downloaded: the outlined "48 MB" pill\n(a tap downloads it, as in the cell)', detail_frame(s, allin, remote, NOTE_EN.split('\n')[0] + '\n' + NOTE_EN.split('\n')[2], 48 << 20)),
              ('the "..." on the page: the cell\'s bottom sheet', detail_frame(s, allin, remote, NOTE_EN.split('\n')[0], 48 << 20, sheet=cell_rows(remote))),
              ('from the search preview: no pill, no "...",\nthe description from the held feed', detail_frame(s, minute, dict(wsj, state='remote', played=False), NOTE_WSJ, 6 << 20, preview=True)),
              ('no description (a local show with no tag):\nthe hint, in the grey line\'s style', detail_frame(s, shows[7], shows[7].eps[1], '', 0))]
    assemble(frames, 3, path)


def nav_strip(s, more):
    """The Shows page's navbar in one capsule state (patch/podcasts.c pg_nav): Back, the small title cut to the room left of the "..." (Import possible), right-aligned to Now Playing; a 320 x 50 strip."""
    o = O
    win = Image.new('RGBA', (W, NAV), (0, 0, 0, 255))
    names = capsule_pieces(more)
    x0 = o['NAV_VIEW_X'] - o['NAV_VIEW_W'] * (len(names) - 1)
    for i, n in enumerate(names): PS.glass(s, win, n, x0 + i * o['NAV_VIEW_W'])
    PS.glass(s, win, 'ah_nav_back', 7, 44); PS.glass(s, win, 'ah_nav_play' if names else 'ah_nav_np', 260, 60)
    px = PI.title_px(s.tree)
    s.text(win, o['NAV_TITLE_X'], 25, PS.fit(s, 'Podcasts', px, x0 - o['NAV_TITLE_X']), px)
    return win


def capsule_panel(s):
    """The two capsule states, one under the other, each with the small title as it is cut."""
    out = Image.new('RGBA', (W, STAT + 2 * (NAV + 22)), (0, 0, 0, 255))
    PI.status_bar(s, out, 0, bg=(0, 0, 0))
    d = ImageDraw.Draw(out)
    for i, (m, cap) in enumerate(((False, 'Now Playing disc'), (True, '... | Now Playing'))):
        y = STAT + i * (NAV + 22)
        d.text((8, y + 4), cap, fill=(0xAA,) * 3, font=PI.ANN)
        out.alpha_composite(nav_strip(s, m), (0, y + 22))
    return out


def search2_sheet(s, shows, path):
    """podcasts-search2.png: the two capsule states with the small title as it is cut; a grid with local and subscribed captions (the "Local" marker)."""
    frames = [("The Shows page's capsule in its two states\n(the small title is cut to the room left of it)", capsule_panel(s)),
              ('Shows grid: a show that is only on the card\nsays Local (the count where it fits)', shows_frame(s, shows, shelf_n=0, scroll=330, end=True, caps='more')[0])]
    assemble(frames, 2, path)
    assemble(frames, 3, path)


def assemble(frames, cols, path, lab=34, pad=12):
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (W + pad) + pad, rows * (STAT + WIN + lab + pad) + pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(frames):
        x, y = pad + (i % cols) * (W + pad), pad + (i // cols) * (STAT + WIN + lab + pad)
        for k, line in enumerate(title.split('\n')): d.text((x, y + k * 16), line, fill=(0xAA,) * 3, font=PI.ANN)
        sheet.paste(im.convert('RGB'), (x, y + lab))
    sheet.save(path, optimize=True)
    print('wrote', path, sheet.size)


def subs_page(s, shows, marked=None, empty=False):
    """The Subscriptions page as patch/podcasts.c paints it (docs/modules/podcasts.md "Subscriptions and OPML"): the Downloads level's rows (a LIST_ART px cover, the name 21 px, the feed status 18 px grey, a
    hairline from LIST_TEXT_X) for every show with a feed, by title (a leading "The " and the case aside); the capsule "..." | Now Playing. marked: a set of titles = select mode (the x, N Selected, Select All,
    a mark column of SG_SEL_COL, the bar with the Unsubscribe pill); empty: no subscription left, the status line."""
    o = O
    subs = [] if empty else sorted((sh for sh in shows if sh.key != 'local'), key=lambda sh: (sh.title[4:] if sh.title.lower().startswith('the ') else sh.title).lower())
    win = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    shift = o['SG_SEL_COL'] if marked is not None else 0
    room = o['LIST_TEXT_W'] - shift
    for r, sh in enumerate(subs):
        y = NAV + o['PP_TITLE_H'] + r * o['PC_ROW_H']
        if y + o['PC_ROW_H'] > WIN - (o['SG_BAR_H'] if marked is not None else 0): break
        _paste(win, cover_img(sh, o['LIST_ART'], o['LIST_R']), o['LIST_ART_X'] + shift, y + o['LIST_ART_Y'])
        s.text(win, o['LIST_TEXT_X'] + shift, y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, PS.fit(s, sh.title, 21, room), 21, WHITE)
        s.text(win, o['LIST_TEXT_X'] + shift, y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, PS.fit(s, sh.sub, 18, room), 18, GREY)
        hline(win, o['LIST_TEXT_X'] + shift, W, y + o['PC_ROW_H'] - 1)
        if marked is not None:
            _paste(win, s.img('selected' if sh.title in marked else 'unselect'), o['LIST_ART_X'] + (shift - 6 - o['SG_MARK']) // 2, y + (o['PC_ROW_H'] - o['SG_MARK']) // 2)
    if marked is None: s.text(win, o['SG_TITLE_X'], NAV + o['PP_TITLE_H'] / 2, 'Subscriptions', o['PP_TITLE_PX'], WHITE)   # (the large heading)
    if empty: s.text(win, W // 2, 180 + 45, 'No subscriptions', 18, WHITE, 'm')
    d = ImageDraw.Draw(win); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0, 255))
    if marked is not None:
        PS.glass(s, win, 'ah_nav_close', 7, 44)
        s.text(win, o['NAV_TITLE_X'], 25, '%d Selected' % len(marked), PI.title_px(s.tree))
        s.text(win, o['SG_SELALL_X'] + 104 - 8 - FONT.width('Select All', 18), 25, 'Select All', 18)
        d.rectangle((0, WIN - o['SG_BAR_H'], W - 1, WIN - 1), fill=(0, 0, 0, 255)); hline(win, 0, W, WIN - o['SG_BAR_H'], PS.HAIR + (255,) if len(PS.HAIR) == 3 else PS.HAIR)
        PS.pill(s, win, o['SG_PILL_X0'], WIN - o['SG_BAR_H'] + (o['SG_BAR_H'] - o['SG_PILL_H']) // 2, 'Unsubscribe', s.img('sg_trash'), w=o['PL_BAR_PILL_W'])
    else:
        PS.glass(s, win, 'ah_nav_back', 7, 44)
        capsule(s, win, 'none' if empty else 'more')
    return frame(s, win, None)


def subs_sheet(s, shows, path):
    """podcasts-subs.png: the Shows page with its Subscriptions row and the "..." sheet that holds Import from Card only, the Subscriptions page, its sheet (Select Shows, Export OPML), its select mode
    with two shows marked, and the empty state."""
    page_rows = [('pc_ic_select', 'Select Shows', '', WHITE), ('pod_ic_export', 'Export OPML', '', WHITE)]
    sf = lambda **k: shows_frame(s, shows, shelf_n=0, **k)[0]
    frames = [('Shows page: the Subscriptions row is a Library row\n(a tap opens the page); no "..." without an import', sf()),
              ('the "..." appears only beside an import source\n(subscriptions.txt or an .opml): Import from Card', sf(sheet=SHOWS_ROWS, caps='more')),
              ('Subscriptions: a row per show with a feed,\nby title; its feed status in grey', subs_page(s, shows)),
              ('its "..." sheet: Select Shows, Export OPML\n(a toast says "Exported 6 shows")', bottom_sheet(s, subs_page(s, shows), page_rows)),
              ('select mode: the x, 2 Selected, marks,\nthe bar with Unsubscribe', subs_page(s, shows, marked={'The Brief', 'Tech Daily'})),
              ('no subscription left', subs_page(s, shows, empty=True))]
    assemble(frames, 3, path)


# ------------------------------------------------------------------ the Downloads page: patch/podcasts.c pg_paint_dls; the layout is tools/pod_show.py downloads_layout

def downloads_page(s, ip, dl, scroll=0, marked=None, line='7 episodes · 217 MB · 18 GB free', empty=False):
    """The Downloads page as patch/podcasts.c paints it (docs/modules/podcasts.md "The Downloads page"): the storage line (15 px grey), the In Progress header and rows, PP_SEC_GAP, the Downloaded header and rows
    (a LIST_ART px cover, the episode 21 px, "show · date · size" or "... · 35m left · ..." 18 px grey, the played check before it, a full width hairline); the capsule "..." | Now Playing. ip: (show, title, line);
    dl: (show, title, tail, played); marked: a set of row indexes = select mode (the x, N Selected, Select All, a mark column of SG_SEL_COL, the bar with the Delete pill); empty: the status line."""
    o = O
    L = pod_show.downloads_layout(len(ip), len(dl), marked is not None)
    shift = o['SG_SEL_COL'] if marked is not None else 0
    im = Image.new('RGBA', (W, max(L['h'], WIN - NAV)), (0, 0, 0, 255))
    s.text(im, o['SG_TITLE_X'], o['PP_TITLE_H'] / 2, 'Downloads', o['PP_TITLE_PX'], WHITE)   # (the large heading scrolls with the content; the navbar takes the small title past SG_COLLAPSE)
    if line: s.text(im, o['PP_LINE_X'], L['y_line'] + o['PP_LINE_H'] / 2, PS.fit(s, line, 15, W - 2 * o['PP_LINE_X']), 15, GREY)
    if ip: s.text(im, o['PP_SHOWS_X'], L['y_ip'] + o['PP_HEAD_H'] / 2, 'In Progress', 20, WHITE)
    if dl: s.text(im, o['PP_SHOWS_X'], L['y_dh'] + o['PP_HEAD_H'] / 2, 'Downloaded', 20, WHITE)
    for i, y in enumerate(L['rows'] if not empty else []):
        if i < len(ip): sh, title, sub = ip[i]; played = False
        else:
            sh, title, tail, played = dl[i - len(ip)]
            sub = PS.fit(s, sh.title, 18, o['LIST_TEXT_W'] - shift - (o['PS_BADGE_CHECK_W'] if played else 0) - FONT.width(tail, 18)) + tail
        _paste(im, cover_img(sh, o['LIST_ART'], o['LIST_R']), o['LIST_ART_X'] + shift, y + o['LIST_ART_Y'])
        s.text(im, o['LIST_TEXT_X'] + shift, y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, PS.fit(s, title, 21, o['LIST_TEXT_W'] - shift), 21, WHITE)
        bx = o['PS_BADGE_CHECK_W'] if played else 0
        if played: _paste(im, glyph16(o['PA_CHECK']), o['LIST_TEXT_X'] + shift - 1, y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] // 2 - 8)
        s.text(im, o['LIST_TEXT_X'] + shift + bx, y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, PS.fit(s, sub, 18, o['LIST_TEXT_W'] - shift - bx), 18, GREY)
        hline(im, 0, W, y + o['PC_ROW_H'] - 1, (0x22, 0x22, 0x22, 255))
        if marked is not None and not (i == 0 and ip and ip[0][2].startswith('Downloading')):
            _paste(im, s.img('selected' if i in marked else 'unselect'), o['LIST_ART_X'] + (shift - 6 - o['SG_MARK']) // 2, y + (o['PC_ROW_H'] - o['SG_MARK']) // 2)
    win = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    win.alpha_composite(im.crop((0, scroll, W, scroll + WIN - NAV)), (0, NAV))
    if scroll:
        for y in range(20): _paste(win, Image.new('RGBA', (W, 1), (0, 0, 0, M.nb_fade_alpha(y, 20))), 0, NAV + y)
    d = ImageDraw.Draw(win); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0, 255))
    if marked is not None:
        PS.glass(s, win, 'ah_nav_close', 7, 44)
        s.text(win, o['NAV_TITLE_X'], 25, '%d Selected' % len(marked), PI.title_px(s.tree))
        s.text(win, o['SG_SELALL_X'] + 104 - 8 - FONT.width('Select All', 18), 25, 'Select All', 18)
        d.rectangle((0, WIN - o['SG_BAR_H'], W - 1, WIN - 1), fill=(0, 0, 0, 255)); hline(win, 0, W, WIN - o['SG_BAR_H'], PS.HAIR + (255,) if len(PS.HAIR) == 3 else PS.HAIR)
        PS.pill(s, win, o['SG_PILL_X0'], WIN - o['SG_BAR_H'] + (o['SG_BAR_H'] - o['SG_PILL_H']) // 2, 'Delete', s.img('sg_trash'), w=o['PL_BAR_PILL_W'])
    else:
        PS.glass(s, win, 'ah_nav_back', 7, 44)
        capsule(s, win, 'none' if empty else 'more')
        if scroll > o['SG_COLLAPSE']: s.text(win, o['NAV_TITLE_X'], 25, PS.fit(s, 'Downloads', PI.title_px(s.tree), o['NAV_VIEW_X'] - o['NAV_TITLE_X']), PI.title_px(s.tree))   # (the large heading has scrolled away: the small title)
    if empty: s.text(win, o['PP_LINE_X'], NAV + o['PDL_LINE_PITCH'] + 8 + o['PS_TITLE_PITCH'] / 2, 'No downloads', 20, DIMT)   # (painted in the content under the storage line: pg_paint_hint)
    return frame(s, win, None)


def confirm_frame(fr, workdir, text):
    """The stock confirm dialog (tools/mod_overlays.py: confirminfo_bg, the highlight alpha 100) over a frame, as tools/preview_overlays.py draws it."""
    import preview_overlays as PO
    from PIL import ImageFont
    fr = fr.copy(); fr.alpha_composite(Image.new('RGBA', fr.size, (0, 0, 0, 100)))
    card = PO.load(workdir, 'confirminfo_bg'); x, y = (W - 260) // 2, (fr.height - 180) // 2
    fr.alpha_composite(card, (x, y)); fr.alpha_composite(Image.new('RGBA', (1, 48), (255, 255, 255, 0x22)), (x + 129, y + 131))
    d = ImageDraw.Draw(fr); font = ImageFont.truetype(os.path.join(workdir, PO.RAW, 'fonts/default.ttf'), 20)
    d.text((W // 2, y + 56), text, font=font, fill='white', anchor='mm'); d.text((x + 65, y + 155), 'No', font=font, fill='white', anchor='mm'); d.text((x + 195, y + 155), 'Yes', font=font, fill='white', anchor='mm')
    return fr


def downloads2_sheet(s, shows, workdir, path):
    """podcasts-downloads2.png: the Shows page's Library rows (downloading, idle) with the slimmer capsule, the Downloads page (both sections, the storage line), scrolled to played and partly played rows, its "..." sheet,
    select mode across both sections, the Delete Played confirm and the empty state."""
    allin, brief, headlines, minute, night, deep, tech = shows[:7]
    ip = [(allin, 'Ep 214: The Real Reason Markets Moved This Quarter', 'Downloading 42%'), (brief, 'Markets open lower, a deal in Brussels and the weather that will not quit', 'Waiting'),
          (headlines, 'Elections, earnings and everything else you missed overnight', "Failed: Can't connect"), (allin, 'Ep 213: Venture Capital Is Broken (And What Replaces It)', 'Paused')]
    dl = [(allin, "Trump's Tariffs, Nvidia's $5T Moment, AI Bubble Debate", ' · 2d ago · 48 MB', False), (night, '第128期｜为什么年轻人不再相信“努力就会有回报”', ' · 5天前 · 31 MB', False),
          (allin, "Amazon's Big Earnings Beat, Intel Gets a Lifeline", ' · 35m left · 66 MB', False), (minute, 'Stocks rally, oil slips and the Fed speaks', ' · Oct 10 · 12 MB', True),
          (brief, 'The week in review', ' · Oct 8 · 24 MB', True), (tech, 'A new chip, a new phone and a new argument', ' · Oct 2 · 19 MB', False),
          (deep, 'Why we collect things', ' · Sep 28 · 38 MB', False), (headlines, 'Elections, earnings and everything else', ' · Sep 21 · 9 MB', True)]
    line = '8 episodes · 1.4 GB · 18 GB free'
    sheet_rows = [('pc_ic_select', 'Select', '', WHITE), ('pc_ic_trash', 'Delete Played Episodes', '', WHITE)]
    page = lambda **k: downloads_page(s, ip, dl, line=line, **k)
    L = pod_show.downloads_layout(len(ip), len(dl))
    played_scroll = L['rows'][len(ip) + 2] - 60
    shows_a = shows_frame(s, shows, shelf_n=0, dl='Downloading 42%', caps='none')[0]
    shows_b = shows_frame(s, shows, shelf_n=0, caps='none')[0]
    frames = [('Shows page: the Library rows, a download running;\nthe capsule is the plain Now Playing disc', shows_a), ('idle: "12 episodes · 1.4 GB"\n(also "2 waiting", "1 paused", "No downloads")', shows_b),
              ('Downloads: storage line, In Progress,\nDownloaded (newest download first)', page()), ('scrolled: the small title in the navbar, a partly played\nrow ("35m left"), played rows with the check', page(scroll=played_scroll)),
              ('the "..." sheet: Select, Delete Played Episodes', bottom_sheet(s, page(), sheet_rows)), ('select mode across both sections\n(the running one cannot be marked)', page(marked={1, 4, 6})),
              ('Delete Played Episodes: the confirm', confirm_frame(page(), workdir, 'Delete all played episodes?')), ('the toast after it (stock message box)', toast_frame(page(scroll=0), workdir, '2 deleted, 105 MB freed')),
              ('nothing downloaded: No downloads', downloads_page(s, [], [], line='18 GB free', empty=True))]
    assemble(frames, 3, path)


def toast_frame(fr, workdir, text):
    """The stock message box (msginfo_bg) over a frame, as tools/preview_overlays.py draws it."""
    import preview_overlays as PO
    from PIL import ImageFont
    fr = fr.copy(); fr.alpha_composite(Image.new('RGBA', fr.size, (0, 0, 0, 100)))
    card = PO.load(workdir, 'msginfo_bg'); x, y = (W - 260) // 2, (fr.height - 180) // 2
    fr.alpha_composite(card, (x, y)); d = ImageDraw.Draw(fr); font = ImageFont.truetype(os.path.join(workdir, PO.RAW, 'fonts/default.ttf'), 18)
    d.text((W // 2, y + 56), text, font=font, fill='white', anchor='mm')
    return fr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir'); ap.add_argument('--logo', default='/tmp/m1plus-allin-check/logo.png'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    global FONT, IMGS
    FONT, IMGS = pod_show.Font(pod_show.font_path(a.workdir)), M.podcast_images()   # (the font of the tree; the build's own atlas, glyphs and sheet glass)
    s = PI.Side(a.workdir, True, a.lang)
    os.makedirs(a.outdir, exist_ok=True)
    shows = make_shows(s, a.logo); allin, brief, headlines, minute, night = shows[:5]
    out = lambda n: os.path.join(a.outdir, 'podcasts-final-' + n + '.png')

    info = build_show(s, allin)[1]; ey = info['episodes_y']; cells = info['cells']
    ninfo = build_show(s, night)[1]
    frames = [('Show page: top (160 px cover, one pill,\ncapsule "... | Now Playing")', show_frame(s, allin)[0]),
              ('scrolled: tinted bar, small title', show_frame(s, allin, ey - 62)[0]),
              ('the show\'s "..." sheet (More sheet style)', show_frame(s, allin, 0, SHOW_ROWS)[0]),
              ('cell "..." on a not downloaded episode', show_frame(s, allin, cells[3][0] - 110, cell_rows(allin.eps[3]))[0]),
              ('cell "..." on a downloaded, partly played one', show_frame(s, allin, cells[2][0] - 110, cell_rows(allin.eps[2]))[0]),
              ('cell "..." on a played and downloaded one', show_frame(s, allin, cells[1][0] - 110, cell_rows(allin.eps[1]))[0]),
              ('red cover (synthetic)', show_frame(s, brief)[0]), ('blue cover (synthetic)', show_frame(s, headlines)[0]), ('green cover (synthetic)', show_frame(s, minute)[0]),
              ('amber cover, a Chinese show: top', show_frame(s, night)[0]), ('Chinese show scrolled: wraps by character,\nno line starts with punctuation', show_frame(s, night, ninfo['episodes_y'] - 62)[0]),
              ('Chinese show: the cell sheet', show_frame(s, night, ninfo['cells'][3][0] - 110, cell_rows(night.eps[3]))[0])]
    assemble(frames, 4, out('show'))

    sf = lambda **k: shows_frame(s, shows, **k)[0]
    assemble([('Shows: the Library rows (Downloads running,\nSubscriptions), Continue Listening x3 below', sf(dl='Downloading 42%')), ('idle: "12 episodes · 1.4 GB", Continue Listening x2', sf(shelf_n=2)),
              ('scrolled: the title collapsed into the navbar', sf(scroll=330)), ('the "..." sheet: Import from Card only', sf(sheet=SHOWS_ROWS, caps='more')),
              ('while refreshing: "Refreshing 2/5"', sf(refreshing=True)), ('end of the grid', sf(end=True))], 3, out('shows'))

    strip = pill_strip(s, allin.tone); col = combos(s, allin)
    sheet = Image.new('RGB', (1340, strip.height + col.height + 36), (0x2A,) * 3)
    sheet.paste(strip, (0, 0)); ImageDraw.Draw(sheet).text((12, strip.height + 8), 'Badge combinations in the cells (date line: check = played, grey disc = on the card)', fill=(0xAA,) * 3, font=PI.ANN)
    sheet.paste(col, (12, strip.height + 30)); sheet.save(out('states'), optimize=True)
    print('wrote', out('states'), sheet.size)
    search_sheet(s, shows, a.workdir, os.path.join(a.outdir, 'podcasts-search.png'))
    detail_sheet(s, shows, os.path.join(a.outdir, 'podcasts-detail.png'))
    search2_sheet(s, shows, os.path.join(a.outdir, 'podcasts-search2.png'))
    subs_sheet(s, shows, os.path.join(a.outdir, 'podcasts-subs.png'))
    downloads2_sheet(s, shows, a.workdir, os.path.join(a.outdir, 'podcasts-downloads2.png'))


if __name__ == '__main__': main()
