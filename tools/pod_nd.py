#!/usr/bin/env python3
"""The asset of the Navidrome root page (patch/ndroot.c, docs/modules/subsonic.md ND-11): the stock navbar (Back, the "..." capsule's left cap on the 214 slot, then Now Playing's
right cap; the hidden Search button is the capsule's left cap on the 168 slot while a server is saved) over a stock list holding one column: the large title, a grey status line under it (a 14 px glyph, nd_st_icon / the spinner nd_st_spin, then "Synced 5m ago"), six menu rows (Albums, Artists, Songs, Playlists,
Favorites, Downloaded: the Main Menu rows' look, a 24 px glyph, the 21 px label, the shared chevron, a hairline) and a grey footer (nd_foot: "2431 songs", the library's footer) under them. The "..." card is the shared view-sort card
with two action rows, Sync Now and Server Settings (patch/ndroot.c; vs_item6 / vs_item7). Hidden over the list, the shared empty state of a page with no server
saved (the Find Cover & Lyrics block: tools/pod_ui.py OA_ES_*): a plug, "Not Connected", one sentence and the Add Server pill, and its own copy of the large title. The rows are named pod_row0..5
(the payload binds them); nothing here has a colour of its own (white, the grey of the cards and the Main Menu's hairline)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PP_TITLE_H, PP_LINE_Y, PP_LINE_H = 52, 52, 20   # patch/offsets.inc: the large title, then the grey line under it (the podcast pages' refresh line)
BIG_H = PP_LINE_Y + PP_LINE_H + 8   # the top item: the large title and the status line under it (the first row's centre lies 80 + 26 px down the page)
ES_DL_GAP = 12      # the empty state's Downloaded pill under the Add Server pill
ROW_H = 52          # tools/pod_ui.py ROW_H
FOOT_H = 64         # the footer's item: patch/offsets.inc SG_FOOT_H (the label SG_FOOT_GAP under the last row) and 12 px of air; the column is then 456 px of the 400 px list, so the offset reaches SG_COLLAPSE 46 (max 56)
SPIN_PX = 14        # the status glyph and the spinner (mod_icons nd_st_*, the Wi-Fi page's wf_spin frames)
SPIN_GAP = 6        # the glyph to the text
ICON_X, ICON_PX = 16, 24
TEXT_X = 56         # the label, after the glyph (patch/radiopage.c RP_TEXT_X)
CHEV_X, TEXT_END = 288, 278   # the shared list chevron's left edge and where a row with one ends its text
HAIR_RGB = '#222222'          # patch/offsets.inc LIST_HAIR
STATUS_PX = 15
GREY = '#8E8E93'            # the empty state's sentence
ROW_GREY = '#AAAAAA'        # the status line: the grey must pass the build's 4.5:1 check on black (tools/mod_theme.py)
ROWS = (('Albums', 'pod_ic_albums'), ('Artists', 'pod_ic_artists'), ('Songs', 'pod_ic_songs'), ('Playlists', 'pod_ic_playlists'), ('Favorites', 'pod_ic_fav'), ('Downloaded', 'pod_sb_download'))


def column():
    """[(name, y, h)] of the column the stock layouter stacks, from y 0 in the scroll view, and its end."""
    y, out = 0, []
    out.append(('nd_top', y, BIG_H)); y += BIG_H
    for i in range(len(ROWS)):
        out.append((f'pod_row{i}', y, ROW_H)); y += ROW_H
    out.append(('nd_end', y, FOOT_H)); y += FOOT_H
    return out, y


def _text_label(name, x, y, w, h, px, colour, align, text=None):
    from pod_ui import Widget, styled
    import pod_i18n
    lab = Widget('hscroll_label', x, y, w, h, [('name', name), pod_i18n.text_prop(text) if text else ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(lab, (st,), 'font_size', str(px))
        styled(lab, (st,), 'text_color', colour)
        styled(lab, (st,), 'text_align_h', align)
        styled(lab, (st,), 'text_align_v', 'middle')
    return lab


def _row(i, label, icon, h):
    """A menu row: a stock list_item (the stock press look), the glyph, the stock label, the chevron and, under all but the last of a group, the hairline."""
    from pod_ui import Widget, styled, STATES, CHEV_BTN_X
    import pod_i18n
    item = Widget('list_item', 0, 0, 310, h, [('name', f'pod_row{i}'), ('style', 'list_item_style')])
    item.children.append(Widget('image', ICON_X, (ROW_H - ICON_PX) // 2, ICON_PX, ICON_PX, [('name', f'pod_icon{i}'), ('image', icon), ('draw_type', 'icon'), ('sensitive', 'false')]))
    item.children.append(Widget('hscroll_label', TEXT_X, 0, TEXT_END - TEXT_X, h, [('name', f'pod_label{i}'), ('style', 'srlabel_leftwhite21_style'), pod_i18n.text_prop(label),
                                                                                   ('only_parent_focus', 'true'), ('ellipses', 'true'), ('yoyo', 'true'), ('loop', 'true')]))
    item.children.append(Widget('image', CHEV_BTN_X, 0, 13, ROW_H - 1, [('name', f'pod_chev{i}'), ('image', 'right_arrow'), ('draw_type', 'icon'), ('sensitive', 'false')]))
    if i < len(ROWS) - 1:
        hair = Widget('view', TEXT_X, h - 1, 310 - TEXT_X, 1, [('name', f'pod_hair{i}'), ('sensitive', 'false')])
        for st in STATES: styled(hair, (st,), 'bg_color', HAIR_RGB)
        item.children.append(hair)
    return item


def build(page):
    from pod_ui import (Widget, styled, navbar, stock_list, nav_fade, cards_spacer, hidden, view_sort_card, wf_image, label as plain_label, SG_FOOT_RGB, VS_SORT_KEYS, _oa_label, _oa_pill, oa_es_layout, OFFSETS, STATES,
                        OA_ES_ICON, OA_ES_TITLE_H, OA_ES_TEXT_H, OA_ES_TEXT_W, OA_ES_PILL_W, OA_ES_PILL_H, OA_ES_TEXT_PX, SCREEN_W, NAVBAR_H)
    import pod_i18n
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title, more_left=True, search=True)   # the capsule [Search | ... | Now Playing]: the "..." (btn_more: the Sync Now / Server Settings card) is the left cap and Search (hidden: patch/ndroot.c) goes in front of it
    hidden(nb.children[0])   # the small title stays (names are kept) but the large one speaks: the column starts with it
    root.children.append(nb)
    lv = stock_list([], True)
    lv.set('name', 'nd_list')
    sv = lv.children[0]

    def big(name):
        w = Widget('label', OFFSETS['SG_TITLE_X'], 0, OFFSETS['SG_TITLE_W'], OFFSETS['PP_TITLE_H'], [('name', name), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
        for st in STATES:
            styled(w, (st,), 'text_color', '#FFFFFF')
            styled(w, (st,), 'font_size', str(OFFSETS['PP_TITLE_PX']))
            styled(w, (st,), 'text_align_h', 'left')
            styled(w, (st,), 'text_align_v', 'middle')
        return w
    placed, end = column()
    for name, y, h in placed:
        if name == 'nd_top':
            it = cards_spacer(name, h)
            it.children.append(big('nd_big'))
            ix = OFFSETS['SG_TITLE_X']
            iy = PP_LINE_Y + (PP_LINE_H - SPIN_PX) // 2
            it.children.append(wf_image('nd_st_icon', ix, iy, SPIN_PX, SPIN_PX, 'nd_st_ok', 'default'))
            it.children.append(hidden(wf_image('nd_st_spin', ix, iy, SPIN_PX, SPIN_PX, 'wf_spin0', 'default')))
            tx = ix + SPIN_PX + SPIN_GAP
            it.children.append(_text_label('nd_status', tx, PP_LINE_Y, OFFSETS['SG_TITLE_X'] + OFFSETS['SG_TITLE_W'] - tx, PP_LINE_H, STATUS_PX, ROW_GREY, 'left'))
        elif name.startswith('pod_row'):
            i = int(name[7:])
            it = _row(i, ROWS[i][0], ROWS[i][1], h)
        else:   # the end: the library's footer, the count of the synced songs (empty until the first sync)
            it = cards_spacer(name, h)
            foot = plain_label('nd_foot', OFFSETS['SG_HDR_X'], OFFSETS['SG_FOOT_GAP'], SCREEN_W - 2 * OFFSETS['SG_HDR_X'], OFFSETS['SG_FOOT_TEXT_H'], '', OFFSETS['SG_FOOT_PX'], SG_FOOT_RGB, 'left')
            foot.set('sensitive', 'false')
            styled(foot, ('normal',), 'text_align_v', 'middle')
            it.children.append(foot)
        it.y = y
        sv.children.append(it)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # patch/ndroot.c shows it while the list is scrolled (at rest it would darken the large title)
    # the shared empty state: the block of the Find Cover & Lyrics page, its own large title (the list's is hidden with it)
    root.children.append(hidden(big('nd_es_big')))
    root.children[-1].y = NAVBAR_H
    iy, ty, xy, py = oa_es_layout('pod_es_plug', 'text', True)
    root.children.append(hidden(Widget('image', (SCREEN_W - OA_ES_ICON) // 2, iy, OA_ES_ICON, OA_ES_ICON, [('name', 'nd_es_icon'), ('image', 'pod_es_plug'), ('draw_type', 'center'), ('sensitive', 'false')])))
    root.children.append(hidden(_oa_label('nd_es_title', 16, ty, 288, OA_ES_TITLE_H, 18, '#FFFFFF', text='Not Connected')))
    root.children.append(hidden(_oa_label('nd_es_text', (SCREEN_W - OA_ES_TEXT_W) // 2, xy, OA_ES_TEXT_W, OA_ES_TEXT_H, OA_ES_TEXT_PX, GREY, text='Navidrome, Gonic, Airsonic and other Subsonic servers', valign='top')))
    pill = _oa_pill('nd_es_pill', (SCREEN_W - OA_ES_PILL_W) // 2, py, OA_ES_PILL_W, OA_ES_PILL_H)
    pill.set(*pod_i18n.text_prop('Add Server'))
    root.children.append(pill)
    dl = _oa_pill('nd_es_dl', (SCREEN_W - OA_ES_PILL_W) // 2, py + OA_ES_PILL_H + ES_DL_GAP, OA_ES_PILL_W, OA_ES_PILL_H)   # downloads stay on the card after Sign Out: reachable without a server
    dl.set(*pod_i18n.text_prop('Downloaded'))
    root.children.append(dl)
    scrim, card = view_sort_card(sort_keys=('Name',) * len(VS_SORT_KEYS), act_keys=('Sync Now', 'Server Settings'), act_glyphs=('pod_ic_vsrefresh', 'pod_ic_vsserver'))
    root.children.extend((scrim, card))   # last: above everything (the "..." card; vs_bind offers the two action rows, Server Settings alone with no server saved)
    return root
