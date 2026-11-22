#!/usr/bin/env python3
"""Approximate PIL mock-up of the Queue page (patch/queuepage.c, docs/modules/queue.md) drawn from the built asset (ui/m1plus_queue.bin) and the payload's constants
(patch/offsets.inc QP_*, LIST_*): the playing track's rounded cover with its title and artist, the icon-only Shuffle and Repeat buttons (off, on, Repeat one), the "Queue" line with its Clear text button,
Up Next (the tracks after the playing one, the Songs page's rows) or the grey "No upcoming songs", the glass Back over the rows when scrolled.
Not pixel-exact AWTK (the text is the project's own text model, the covers are stand-in gradients); the pill and row geometry is the Songs page's (tools/preview/preview_songs.py).

  preview_queue.py WORKDIR OUT.png [--lang CODE]
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import awtk_ui
import preview_icons as PI
import preview_songs as PS

W, WIN, RAW = 320, 450, PI.RAW
O = PI.offsets()
GREY, MUTED = (0xAA, 0xAA, 0xAA), (0x9C, 0x9C, 0x9C)
ROW, ART, ART_X, ART_Y, TEXT_X = O['LIST_ROW_H'], O['LIST_ART'], O['LIST_ART_X'], O['LIST_ART_Y'], O['LIST_TEXT_X']
TOP, TEXT_END = O['QP_TOP'], O['QP_TEXT_END']
rgb4 = lambda w: (w & 255, (w >> 8) & 255, (w >> 16) & 255)    # 0xAABBGGRR of offsets.inc: the page's colour words (a color_t)
PILL_ON, PILL_ON_DOWN, PILL_OFF = (rgb4(O['QP_PILL_ON'])), rgb4(O['QP_PILL_ON_DOWN']), rgb4(O['QP_PILL_OFF'])

# title, artist, cover colour (index into PI.ALBUMS)
QUEUE = [('Chorus Complains', 'Driftless Pony Club', 3), ('When We Live In Circles and Other Long Titles', 'Driftless Pony Club', 3),
         ('House of 1982 Built Like a Ship', 'Driftless Pony Club', 3), ('He Plans Houses Like Trees', 'Driftless Pony Club', 3),
         ('So What', 'Miles Davis', 0), ('Freddie Freeloader', 'Miles Davis', 0), ('Blue in Green', 'Miles Davis', 0), ('All Blues', 'Miles Davis', 0),
         ('Come Together', 'The Beatles', 2), ('Something', 'The Beatles', 2), ('Hey Jude', 'The Beatles', 2), ('Let It Be', 'The Beatles', 2),
         ('春よ、来い', '松任谷由実', 10), ('夜に駆ける', 'YOASOBI', 10)]


def content(s, playing=1, shuffle=False, repeat=None, edit=True):
    n = len(QUEUE) - playing - 1    # Up Next: the tracks after the playing one (the queue's own order, shuffled or not)
    im = Image.new('RGBA', (W, max(WIN, TOP + n * ROW + O['QP_BOTTOM'])), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    title, artist, ci = QUEUE[playing]
    cx, cy, c, r = O['QP_COVER_X'], O['QP_COVER_Y'], O['QP_COVER'], O['QP_COVER_R']
    im.alpha_composite(PI.rounded(PI.sample_cover(PI.ALBUMS[ci][2], c), r), (cx, cy))
    room = O['QP_TEXT_W']
    s.text(im, O['QP_TEXT_X'], O['QP_TITLE_Y'] + O['QP_TITLE_H'] / 2, s.clip(title, 20, room), 20)
    s.text(im, O['QP_TEXT_X'], O['QP_ARTIST_Y'] + O['QP_ARTIST_H'] / 2, s.clip(artist, 16, room), 16, GREY)
    for glyph, on, x in (('sg_shuffle', shuffle, O['QP_PILL_X0']), ('sg_repeat1' if repeat == 'one' else 'sg_repeat', repeat is not None, O['QP_PILL_X1'])):    # icon only, centred
        PS.round_rect(im, x, O['QP_PILL_Y'], O['QP_PILL_W'], PS.PILL_H, PS.PILL_R, PILL_ON if on else PILL_OFF)
        g = s.img(glyph + '_on' if on else glyph); im.alpha_composite(g, (x + (O['QP_PILL_W'] - g.width) // 2, O['QP_PILL_Y'] + (PS.PILL_H - g.height) // 2))
    s.text(im, O['SG_HDR_X'], O['QP_HEAD_Y'] + O['QP_HEAD_H'] / 2, PS.tr(s, 'Queue'), 20)
    if n: s.text(im, O['QP_CLEAR_X'] + O['QP_CLEAR_W'], O['QP_CLEAR_Y'] + O['QP_CLEAR_H'] / 2, PS.tr(s, 'Clear'), 17, MUTED, 'r')    # Clear: right aligned to x 310, centred on the line, only while songs follow
    if not n: s.text(im, O['SG_HDR_X'], TOP + O['QP_EMPTY_Y'] + O['QP_EMPTY_H'] / 2, PS.tr(s, 'No upcoming songs'), 16, MUTED)
    more = PS.dots(s)   # the rows' "..." while the page offers the edit (patch/queuepage.c qp_edit_on); the texts end RM_INK_GAP before its ink
    text_end = PS.dots_x(PS.more_right(False), False) + PS.INK_X - PS.INK_GAP if edit else TEXT_END
    for i in range(n):
        t, a, k = QUEUE[playing + 1 + i]; y = TOP + i * ROW
        d.rectangle((TEXT_X, y + ROW - 1, TEXT_END - 1, y + ROW - 1), fill=PS.HAIR)
        im.alpha_composite(PI.rounded(PI.sample_cover(PI.ALBUMS[k][2], ART), O['LIST_R']), (ART_X, y + ART_Y))
        s.text(im, TEXT_X, y + O['LIST_TITLE_Y'] + O['LIST_TITLE_H'] / 2, s.clip(t, 20, text_end - TEXT_X), 20)
        s.text(im, TEXT_X, y + O['LIST_SUB_Y'] + O['LIST_SUB_H'] / 2, s.clip(a, 18, text_end - TEXT_X), 18, GREY)
        if edit: im.alpha_composite(more, (PS.dots_x(PS.more_right(False), False), y + (ROW - 1 - PS.DOTS_PX) // 2))
    return im


def page(s, scroll=0, sheet=False, **kw):
    tall = content(s, **kw)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    scroll = max(0, min(scroll, tall.height - WIN))
    im.alpha_composite(tall.crop((0, scroll, W, scroll + WIN)), (0, 0))
    PS.glass(s, im, 'ah_nav_back', 7, 44)    # the glass Back floats over the rows
    if sheet: PS.row_menu(s, im, keys=('Play Next', 'Play After', 'Remove from Queue'), glyphs=('rm_ic_next', 'rm_ic_after', 'pod_ic_remove_red'))    # the "..." sheet (three rows, the three-row glass)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    asset = awtk_ui.parse(open(os.path.join(a.workdir, RAW, 'ui', 'm1plus_queue.bin'), 'rb').read())
    assert asset.find('btn_repeat') is not None and asset.find('view_queue') is not None, 'not the Queue asset'
    panels = [('Playing the 2nd track, modes off', page(s, playing=1)),
              ('Shuffle on, Repeat all: independent', page(s, playing=1, shuffle=True, repeat='all')),
              ('Repeat one', page(s, playing=1, repeat='one')),
              ('Repeat all, scrolled', page(s, playing=1, repeat='all', scroll=300)),
              ('The last track playing: nothing follows', page(s, playing=len(QUEUE) - 1)),
              ('A row\'s "..." tapped: the sheet', page(s, playing=1, sheet=True)),
              ('Folder playback or DLNA: no "..."', page(s, playing=1, edit=False))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
