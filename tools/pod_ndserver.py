#!/usr/bin/env python3
"""The asset of the Navidrome Server page (patch/ndserver.c, docs/modules/subsonic.md ND-12): the stock navbar over the Settings cards (tools/pod_settings.py numbers), two cards:
Server URL / Username / Password (a grey value and the chevron, no glyph) and Sync Now / Sign Out (plain action rows). The rows are the cards builder's own (tools/pod_ui.py cards_row),
named pod_row0..4 with pod_label<i> and pod_value0..2, which the payload fills and binds. No status line: the root page shows the status. No colour of its own (the cards' greys)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pod_pages, pod_settings as ST

BIG_H = 60                                     # the large title's item: the Podcasts levels' title (PP_TITLE_H 52 high at SG_TITLE_X) and 8 px of air above the first card
VALUE_RIGHT = ST.value_box()[0] + ST.VALUE_W   # the value's right edge in its row: patch/ndserver.c NS_VALUE_RIGHT
LABEL_X = ST.CM + ST.PAD                       # the labels' left edge (no glyph): NS_LABEL_X


def build(page):
    from pod_ui import Widget, styled, navbar, stock_list, nav_fade, cards_spacer, cards_row, hidden, OFFSETS, STATES
    import pod_i18n
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    nb = navbar(page.title)
    hidden(nb.children[0])   # the small title is hidden at rest and shown by patch/ndserver.c once the large one below has scrolled away (pod_title_gone)
    root.children.append(nb)
    lv = stock_list([], True)
    sv = lv.children[0]
    placed, end = ST.layout(page.layout)
    pieces = ST.pieces(page.layout)
    n_gap = i = 0
    for it, y in placed:
        if it == ST.TOP:
            top = cards_spacer('pod_top', BIG_H)
            big = Widget('label', OFFSETS['SG_TITLE_X'], 0, OFFSETS['SG_TITLE_W'], OFFSETS['PP_TITLE_H'], [('name', 'pod_big'), pod_i18n.text_prop(page.title), ('sensitive', 'false')])
            for st in STATES:
                styled(big, (st,), 'text_color', '#FFFFFF')
                styled(big, (st,), 'font_size', str(OFFSETS['PP_TITLE_PX']))
                styled(big, (st,), 'text_align_h', 'left')
                styled(big, (st,), 'text_align_v', 'middle')
            top.children.append(big)
            sv.children.append(top)
        elif it == ST.END: sv.children.append(cards_spacer('pod_end', end_h(y + BIG_H - ST.CM)))
        elif it is pod_pages.GAP: sv.children.append(cards_spacer(f'pod_gap{n_gap}', ST.GAP_H)); n_gap += 1
        else:
            row = cards_row(i, it, pieces[i], pieces[i] in ('single', 'bot'), icon=False)
            if it.action == pod_pages.ACT_NDACT and it.label == 'Sync Now': sync_status(row, i)   # the Sync Now row's grey status and the spinner before it (patch/ndserver.c ns_sync_show)
            sv.children.append(row); i += 1
        sv.children[-1].y = y + (BIG_H - ST.CM if it != ST.TOP else 0)
    root.children.append(lv)
    root.children.append(nav_fade(shown=False))   # shown by the page while the list is scrolled
    return root


SYNC_W, SYNC_SPIN_PX = 150, 14                  # the Sync Now row's value box (right aligned at VALUE_RIGHT, no chevron) and its spinner (the Wi-Fi page's frames), which the payload places before the text


def sync_status(row, i):
    """The Sync Now row's status: a grey value ("Syncing…", "Synced 5m ago") as the other rows' and a hidden spinner; the payload fills, fits and turns them."""
    from pod_ui import Widget, styled, hidden, wf_image
    val = Widget('hscroll_label', VALUE_RIGHT - SYNC_W, 0, SYNC_W, ST.ROW_H, [('name', f'pod_value{i}'), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
    for st in ('normal', 'disable', 'focused'):
        styled(val, (st,), 'font_size', str(ST.VALUE_PX))
        styled(val, (st,), 'text_color', ST.GREY)
        styled(val, (st,), 'text_align_h', 'right')
        styled(val, (st,), 'text_align_v', 'middle')
    row.children.append(val)
    row.children.append(hidden(wf_image('ns_spin', VALUE_RIGHT - SYNC_W, (ST.ROW_H - SYNC_SPIN_PX) // 2, SYNC_SPIN_PX, SYNC_SPIN_PX, 'wf_spin0', 'default')))


END_MARGIN = 10                                # the offset reaches the collapse with 10 px to spare


def end_h(y):
    """The end spacer's height for an end at y: the content is 350 px of the 400 px list, which would never scroll, so the spacer pads it to the list plus the collapse offset (the large title can scroll away and the
    small one fade in, as on every large-title page; the bounce below the last card is the price)."""
    from pod_ui import OFFSETS, CLIENT_H, NAVBAR_H
    return max(ST.END_H, CLIENT_H - NAVBAR_H + OFFSETS['SG_COLLAPSE'] + END_MARGIN - y)


# The Sign In page (patch/ndserver.c nl_open, docs/modules/subsonic.md): the Join Wi-Fi Network page's layout (tools/pod_ui.py build_wifiother_page) for the login. One Settings card of three 48 px rows (Server
# URL, Username, Password) with our keyboard embedded: kb_field moves to the row being typed in, the other rows show their value in a static label (nl_v<i>) or, while empty, the grey placeholder (nl_h<i>), which is
# also the row's name (no label column: a Username label is up to 171 px in 13 languages and a URL needs the room). Three buttons take the taps (nl_hit<i>), the eye is on the Password row, and under the card one
# line holds the spinner and "Connecting..." (nl_spin, nl_busy) or the error (nl_err). Everything ends above the candidate strip (y 234): rows y 56..200, the line y 208..228. No colour of its own.
NL_ROWS = ('Server URL', 'Username', 'Password')
NL_ROW_H, NL_Y0, NL_X = 48, 56, 24
NL_FIELD_W, NL_TW = 272, 232            # the field's box (card ink edge to ink edge; the clear button at its right) and the text room of each field (the Password row's ends before the eye)
NL_LINE_Y, NL_LINE_H, NL_LINE_PX = 208, 20, 16
NL_SPIN_PX, NL_BUSY_X = 14, 46          # the spinner (the Wi-Fi page's frames) at x 24, the "Connecting..." text after it


def build_login(page):
    import pod_i18n
    from pod_ui import Widget, styled, navbar, label, hidden, kb_view, kb_field_widget, eye_button, keyboard_pad_widgets, wf_image, WK_CARD_X, WK_CARD_W, WK_FIELD_PX, WK_EYE_X, WK_EYE_W
    import pod_keyboard as PK
    root = Widget('window', 0, 0, 0, 0, [('name', page.name)])
    styled(root, ('normal', 'disable', 'focused'), 'bg_color', '#000000')
    root.children.append(navbar(page.title))
    n = len(NL_ROWS)
    root.children.append(kb_view('nl_card', WK_CARD_X, NL_Y0, WK_CARD_W, n * NL_ROW_H, ST.CARD_RGB, ST.CARD_R))
    for i in range(1, n):
        hair = Widget('view', NL_X, NL_Y0 + i * NL_ROW_H - 1, ST.CM + ST.CARD_W - NL_X, 1, [('name', f'nl_hair{i - 1}'), ('sensitive', 'false')])
        for st in ('normal', 'disable', 'focused'): styled(hair, (st,), 'bg_color', ST.CARD_HAIR_RGB)
        root.children.append(hair)
    def value(name, i, colour, english=None):
        lab = label(name, NL_X, NL_Y0 + i * NL_ROW_H, NL_FIELD_W, NL_ROW_H, '', WK_FIELD_PX, colour, 'left')
        if english: lab.set(*pod_i18n.text_prop(english))
        lab.set('sensitive', 'false')
        styled(lab, ('normal',), 'text_align_v', 'middle')
        return hidden(lab)
    for i, english in enumerate(NL_ROWS):
        root.children.append(value(f'nl_v{i}', i, PK.KB_INK))
        root.children.append(value(f'nl_h{i}', i, PK.KB_GREY, english))
    for i in range(n):
        w = (WK_EYE_X - WK_CARD_X) if i == n - 1 else WK_CARD_W
        root.children.append(Widget('button', WK_CARD_X, NL_Y0 + i * NL_ROW_H, w, NL_ROW_H, [('name', f'nl_hit{i}'), ('enable', 'true'), ('style', 'img_btn_style')]))
    root.children.append(kb_field_widget(NL_X, NL_Y0, NL_FIELD_W, NL_ROW_H, (NL_ROW_H - 22) // 2))
    root.children.append(eye_button('nl_eye', WK_EYE_X, NL_Y0 + (n - 1) * NL_ROW_H, WK_EYE_W, NL_ROW_H))
    root.children.append(hidden(wf_image('nl_spin', NL_X, NL_LINE_Y + (NL_LINE_H - NL_SPIN_PX) // 2, NL_SPIN_PX, NL_SPIN_PX, 'wf_spin0', 'default')))
    def line(name, x, english):
        lab = label(name, x, NL_LINE_Y, WK_CARD_W - 2 * (NL_X - WK_CARD_X) - (x - NL_X), NL_LINE_H, '', NL_LINE_PX, ST.GREY, 'left')
        if english: lab.set(*pod_i18n.text_prop(english))
        styled(lab, ('normal',), 'text_align_v', 'middle')
        return hidden(lab)
    root.children.append(line('nl_busy', NL_BUSY_X, 'Connecting…'))
    root.children.append(line('nl_err', NL_X, None))
    root.children += keyboard_pad_widgets()
    return root
