"""Cover Flow: the page, the cache build, the worker, the depth renderer against the host build, touch, hit tests."""
import os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)


def run(ctx):
    expect, page = ctx.expect, ctx.page
    cover_open = PSYMS['coverflow_open']
    cover_row = next(i for i, r in enumerate(page.rows) if r.action == pod_pages.ACT_COVER)
    # 7. The menu's Cover Flow row opens the Cover Flow page.
    m = cover_machine()
    m.call(PSYMS['on_row'], a0=PSYMS['pod_rows_0'] + 12 * cover_row, count=2000000)
    expect(('window_open', 'm1plus_cover') in m.calls, 'the Cover Flow row opens m1plus_cover')

    # 8. Opening with a complete cache: no build, no thread, the depth shelf (its position the payload's own:
    #    no stock slide_menu, no widget per album), the touch layer, the captions set and the first album centred.
    m = cover_machine(albums=3)
    v = m.call(cover_open, count=5000000)
    expect(v == 0, 'coverflow_open returns 0')
    expect('pthread_create' not in m.names(), 'a complete cache starts no thread')
    expect(not any(c[0] in ('slide_menu', 'image_create') for c in m.calls) and [c[0] for c in m.calls].count('view') == 1,
           'depth mode creates no slide_menu and no widget per album, only the touch layer')
    expect(shelf_value(m) == 0 and shelf_off(m) == 0, 'the shelf starts on the first album, at rest')
    expect(('widget_set_text_utf8', m.widgets['label_album'], 'Album 0') in m.calls, 'album caption')
    expect(('widget_set_text_utf8', m.widgets['label_artist'], 'Artist 0') in m.calls, 'artist caption')
    expect(('mkdir', '/mnt/mmc/.m1plus/covers') not in m.calls, 'no cache directory needed when complete')

    # 9. Tap the centre cover: the stock Albums sequence and the stock album page. The stock album
    #    list goes back into *pdeq_showlist (loadAlbumList(0xf003, 0), what album_page_init runs), the
    #    cover-task list is rebuilt from it (albumcoverinfo_init, @0x4dcf9c) and albuminfo_page opens
    #    with the context the stock row handler builds (@0x523d94): class | row << 16. The page itself
    #    keeps no track list, header or play code of its own any more.
    m.tap(O['CF_CX'])
    names = [c[0] for c in m.calls if c[0] in ('loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context')]
    expect(names == ['loadAlbumList', 'albumcoverinfo_init', 'navigator_to_with_context'],
           f'the stock queries run, then the page opens ({names})')
    seq = [c[0] for c in m.calls if c[0] in ('albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context')]
    expect(seq == ['albumcoverinfo_init', 'batchadd_albumcover_task', 'navigator_to_with_context']
           and ('batchadd_albumcover_task', 0, 0) in m.calls,
           f'the cover thread is released (taskstate 2 -> 1) before the page queues its cover task ({seq})')
    expect(('loadAlbumList', O['CLASS_ALBUMS'], 0, '') in m.calls, 'the stock Albums query: loadAlbumList(0xf003, 0)')
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 0) in m.calls,
           'the centre cover opens the stock albuminfo_page with context 0xf003 | row 0 << 16')
    cls, row, shown = m.opened_album
    expect(m.deques[shown] == m.showlist and ('albumcoverinfo_init', shown) in m.calls,
           'the cover-task list is built from the album list the page will read its row from')
    expect(not any(n in m.names() for n in ('list_item_create', 'loadSongList')),
           'no track list, no tracks query and no play code on the Cover Flow page any more')
    expect(not any(n in PSYMS for n in ('on_track', 'ap_on_play', 'ap_on_shuffle', 'ap_paint', 'ap_play', 'to_tracks')),
           'the custom album page is gone from the payload')
    # the row is the album in the centre; the saved album (the main page's memory) follows the tap
    m2 = cover_machine(albums=3); m2.call(cover_open, count=5000000)
    put_value(m2, 2)
    m2.call(PSYMS['on_changed'], count=2000000)
    m2.tap(O['CF_CX'])
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 2) in m2.calls,
           'the centre album (2) is the row of the context')
    expect(m2.opened_album[2] != 0 and m2.deques[m2.opened_album[2]][2] == m2.showlist[2], 'and that row of the list is its album')

    # 10. The stock queries are repeated on every open: something else may have reused the browsing
    #     record or the list since (the page is open again after Back from the album page).
    m.tap(O['CF_CX'])
    expect(m.names().count('loadAlbumList') == 1 and 'albumcoverinfo_init' in m.names(), 'a second open runs them again')
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 0) in m.calls, 'and opens the page again')

    # 11. Back: the covers screen leaves the page (there is no tracks screen to go back to).
    on_back = PSYMS['on_back']
    m.call(on_back, count=200000)
    expect('navigator_back' in m.names(), 'Back on the covers screen leaves the page')
    expect('navigator_back' in m.names(), 'Back on the covers screen leaves the page')

    # 12. Tapping a cover that is not the centre scrolls to it instead of opening it.
    put_value(m, 0)
    m.tap(O['CF_CX'] + 100)      # the right-hand neighbour
    expect('navigator_to_with_context' not in m.names(), 'a side cover opens no album')
    m.settle()
    expect(('set_value', 1) in m.calls, 'a right-hand tap brings the next album to the centre')
    expect(shelf_off(m) == 0, 'the offset is back to 0 after the commit')

    # 12b. A slow drag to the left by a little more than DRAG_PX moves one album on; the shelf
    #      follows the finger while it moves, and the pointer is grabbed and released.
    put_value(m, 0)
    m.touch('down', 200, t=1000); grabbed = ('widget_grab', m.widgets['view_covers'], m.widgets['view']) in m.calls
    m.touch('move', 150, t=1300)
    mid = struct.unpack('<i', struct.pack('<I', shelf_off(m) & 0xffffffff))[0]
    m.touch('move', 100, t=1600)
    m.touch('up', 100, t=1900)
    released = any(c[0] == 'widget_ungrab' for c in m.calls)
    m.settle()
    expect(grabbed and released, 'the touch layer grabs the pointer for the drag and releases it')
    expect(mid != 0 and mid < 0, f'the shelf follows a leftward drag (xoffset {mid})')
    expect(('set_value', 1) in m.calls, 'a drag of one cover spacing advances one album')

    # 12c. A fast flick coasts further than the finger went (a longer shelf: this one's ends stop it).
    m = cover_machine(albums=8); m.call(PSYMS['coverflow_open'], count=5000000)
    put_value(m, 1)
    m.touch('down', 250, t=5000); m.touch('move', 200, t=5020); m.touch('move', 150, t=5040)
    m.touch('up', 150, t=5050)
    m.settle()
    offs = [c[1] for c in m.calls if c[0] == 'set_offset']
    far = max(abs(o) for o in offs) if offs else 0
    expect(far > 2 * O['CF_VIEW_H'], f'a flick coasts more than two albums (|xoffset| up to {far})')

    # 12d. A drag to the right from the first album does not wrap to the last (the end: see the bounded shelf tests).
    m = cover_machine(albums=3); m.call(PSYMS['coverflow_open'], count=5000000)
    put_value(m, 0)
    m.touch('down', 60, t=9000); m.touch('move', 120, t=9300); m.touch('move', 160, t=9600)
    m.touch('up', 160, t=9900)
    m.settle()
    expect(not any(c[0] == 'set_value' for c in m.calls) and shelf_value(m) == 0 and shelf_off(m) == 0, 'dragging right from the first album stays on it: no wrap to the last')

    # 12e. An aborted gesture (stock sends 0x107) releases the grab and snaps back.
    put_value(m, 1)
    m.touch('down', 200, t=12000); m.touch('move', 180, t=12100); m.touch('abort', 180, t=12150)
    expect(any(c[0] == 'widget_ungrab' for c in m.calls), 'an abort releases the grab')
    m.settle()
    expect(shelf_off(m) == 0, 'an abort snaps back to the album')
    gesture_tests(ctx)
    shelf_tests(ctx)

    # 13. Close: the timer is dropped, the worker joined, the frame and list freed.
    m.call(PSYMS['on_destroy'], count=2000000)
    expect('deque_destroy' in m.names(), 'the album copy is freed')
    expect(('rename', '/mnt/mmc/.m1plus/coverflow-position.tmp', '/mnt/mmc/.m1plus/coverflow-position') in m.calls, 'the last album is saved on close')

    # 14. First run: no cache files -> jobs, a thread, the progress label and Cancel.
    m = cover_machine(albums=3, cached=False)
    m.call(cover_open, count=5000000)
    expect(m.calls.index(('mkdir', '/mnt/mmc/.m1plus')) < m.calls.index(('mkdir', '/mnt/mmc/.m1plus/covers')), 'the card folder, then the cache directory in it, are created')
    expect('pthread_create' in m.names(), 'the build thread is started')
    expect(('widget_set_visible', m.widgets['btn_cancel'], 1) in m.calls, 'Cancel is shown')
    expect(any(c[0] == 'timer_add' for c in m.calls), 'the progress timer runs')
    expect('view' not in [c[0] for c in m.calls], 'the covers wait for the build')

    # 15. The worker itself: for each album, the two stock art calls under parse_cover_mutex, the
    #     result renamed into place, and an empty marker when both fail.
    lock = pod.DATA['PARSE_COVER_MUTEX'][0]
    m.album_cover = 1
    m.call(PSYMS['cc_worker'], count=5000000)
    seq = [c for c in m.calls if c[0] in ('lock', 'unlock', 'taglib_album_picture', 'toolsGetAlbumCover', 'toolsGetExternCover')]
    expect([c[0] for c in seq[:5]] == ['lock', 'taglib_album_picture', 'unlock', 'lock', 'toolsGetAlbumCover'] and seq[0] == ('lock', lock) and seq[5] == ('unlock', lock),
           f'taglib and then the stock art call are each made under parse_cover_mutex ({seq[:6]})')
    expect(sum(1 for c in m.calls if c[0] == 'rename' and c[2].endswith('.jpg')) == 3, 'every album\'s thumbnail is renamed into place')
    expect([c for c in m.calls if c[0] == 'toolsGetExternCover'] == [], 'the folder image is only a fallback')
    # the thumbnails are extracted at the larger size, into files named for it
    expect(getattr(m, 'cover_size', None) == (O['ART_SIZE'], O['ART_SIZE']),
           f'the thumbnails are {O["ART_SIZE"]} px ({getattr(m, "cover_size", None)})')
    dst = [c[2] for c in m.calls if c[0] == 'rename' and c[2].endswith('.jpg')]
    expect(dst and all(d.endswith(f'-{O["ART_SIZE"]}.jpg') and d in cache_paths(m, 3) for d in dst),
           f'a {O["ART_SIZE"]} px thumbnail never takes the name of a 140 px one ({dst[:1]})')

    m3 = cover_machine(albums=1, cached=False)
    m3.call(cover_open, count=5000000)
    m3.album_cover = m3.extern_cover = 0
    m3.call(PSYMS['cc_worker'], count=5000000)
    expect(any(c[0] == 'toolsGetExternCover' for c in m3.calls), 'no embedded art -> the folder image')
    expect(any(c[0] == 'fopen' and c[2] == 'w' for c in m3.calls), 'no art at all leaves an empty marker')

    # 15b. A cache write that fails is not "no art" (audit): extracted but not published -> no marker, a later open retries
    m4 = cover_machine(albums=1, cached=False)
    m4.call(cover_open, count=5000000)
    final = cache_paths(m4, 1)[0]
    m4.album_cover = 1; m4.fail.add(('rename', final))
    m4.call(PSYMS['cc_worker'], count=5000000)
    expect(final not in m4.present and final not in m4.files and not any(c[0] == 'fopen' and c[1] == final for c in m4.calls),
           'a failed rename leaves the final path absent: no empty marker')
    expect(not [p for p in m4.files if p.endswith('.tmp')], 'and the temp file is removed')
    m4b = cover_machine(albums=1, cached=False)
    m4b.call(cover_open, count=5000000)
    m4b.album_cover = m4b.extern_cover = 0
    m4b.call(PSYMS['cc_worker'], count=5000000)
    expect(cache_paths(m4b, 1)[0] in m4b.present and m4b.files.get(cache_paths(m4b, 1)[0]) == 0, 'a genuine absence of art still leaves the empty marker')

    # 15c. The progress timer cannot be created (audit): the screen never waits for a callback that cannot come
    m5 = cover_machine(albums=2, cached=False); m5.timer_fail = True
    m5.call(cover_open, count=5000000)
    expect('pthread_create' in m5.names() and 'pthread_join' not in m5.names() and build_state(m5)['orphan'] == 1, 'initial timer refused: the worker is cancelled and orphaned, not joined')
    expect('view' in [c[0] for c in m5.calls] and ('widget_set_visible', m5.widgets['btn_cancel'], 1) not in m5.calls,
           'initial timer refused: the covers show, no Preparing screen with a Cancel nobody needs')
    m6 = cover_machine(albums=2, cached=False)
    m6.call(cover_open, count=5000000)
    m6.timer_fail = True; m6.call(PSYMS['on_poll'], count=5000000)
    expect('pthread_join' not in m6.names() and build_state(m6)['orphan'] == 1 and 'view' in [c[0] for c in m6.calls],
           'a refused re-arm: the worker is cancelled and orphaned, and the covers show')

    # 16. Cancel: the thread is told to stop (not waited for), the timer dropped, the covers shown.
    m.call(PSYMS['on_cancel'], count=5000000)
    expect('pthread_join' in m.names() and build_state(m)['jobs'] == 0, 'Cancel joins a worker that has finished (it ran above) and frees the set')
    m7 = cover_machine(albums=3, cached=False); m7.call(cover_open, count=5000000); m7.call(PSYMS['on_cancel'], count=5000000)
    expect('pthread_join' not in m7.names() and build_state(m7)['orphan'] == 1, 'Cancel with a job in flight orphans the worker, no join')
    expect('timer_remove' in m.names(), 'Cancel drops the progress timer')
    expect('view' in [c[0] for c in m.calls], 'Cancel shows the covers')

    # 17. No card or no space: no thread, straight to the covers with whatever is cached.
    m = cover_machine(albums=2, cached=False); m.free_mb = 2
    m.call(cover_open, count=5000000)
    expect('pthread_create' not in m.names(), 'no free space -> no build')
    expect('view' in [c[0] for c in m.calls], 'no free space still shows the covers')
    m = cover_machine(albums=2, cached=False); m.thread_ok = False
    m.call(cover_open, count=5000000)
    expect('view' in [c[0] for c in m.calls], 'a refused thread still shows the covers')

    # 18. An empty library: the message, no slide_menu, no thread.
    m = cover_machine(albums=0)
    v = m.call(cover_open, count=2000000)
    expect(v == 0 and 'view' not in [c[0] for c in m.calls], 'an empty library draws no covers')
    expect(any(c[0] == 'widget_set_text_utf8' and 'Update Local Music' in str(c[2]) for c in m.calls),
           'an empty library says to update the library')
    expect('pthread_create' not in m.names(), 'an empty library starts no thread')

    # 19. A broken or foreign asset (a widget missing): leave the page rather than work on half of it.
    m = cover_machine()
    del m.widgets['label_status']
    v = m.call(cover_open, count=2000000)
    expect(v == 0xffffffff and 'navigator_back' in m.names(), 'a missing widget closes the page')
    m = cover_machine(); m.window = 0
    expect(m.call(cover_open, count=200000) == 0xffffffff, 'window_open failure returns -1')

    missing_only_tests(ctx)

    # 20. The depth renderer on the real MIPS code: paint the covers and compare the frame with
    #     the host build of the same renderer (test/coverflow.py), pixel for pixel.
    m = cover_machine(albums=5).count()
    m.call(cover_open, count=5000000)
    put_value(m, 2)
    put_off(m, O['CF_VIEW_H'] // 4)      # a quarter of a step into a drag
    event = m.alloc(0x40); m.u.mem_write(event, bytes(0x40))
    canvas = 0x22220000
    m.setword(event + O['EVENT_PAINT_CANVAS'], canvas)
    m.call(PSYMS['on_paint'], a0=0, a1=event, count=400000000)
    print(f'  depth frame: {m.icount:,} payload instructions '
          f'({O["CF_VIEW_W"]}x{O["CF_VIEW_H"]}, ART_SIZE {O["ART_SIZE"]})')
    expect(('canvas_draw_image', m.bitmap[0]) in m.calls, 'the frame is drawn on the canvas')
    b, data, w, h = m.bitmap
    expect((w, h) == (O['CF_VIEW_W'], O['CF_VIEW_H']), 'the frame is the CF_VIEW size')
    frame = bytes(m.u.mem_read(data, w * h * 4))
    # p = value - xoffset / h, so a positive xoffset puts the shelf a quarter step *before* the
    # centre album: frac = -(xoffset / h) in 16.16.
    host = host_frame(-((O['CF_VIEW_H'] // 4) * 65536 // O['CF_VIEW_H']))
    expect(frame == host, 'the payload renders the same frame as the host build')

    # 21. No frame bitmap: the flat fallback puts the cached art on the stock images near the
    #     centre and the placeholder elsewhere, and paint draws nothing of its own.
    m = cover_machine(albums=9)
    m.bitmap_ok = False
    m.call(cover_open, count=5000000)
    pics = [c[2] for c in m.calls if c[0] == 'image_base_set_image']
    expect(pics, 'the flat fallback sets pictures on the stock images')
    expect(sum(1 for p in pics if p.startswith('file://')) == 3 + 1,
           f'real art only within ART_NEAR of the centre, the shelf having no wrapped side (got {pics})')
    expect(sum(1 for p in pics if p == 'p_default') == 9 - 4, 'the rest keep the placeholder')
    slide = m.widgets.get('slide_menu')
    expect(slide and len(m.children.get(slide, [])) == 9 and m.props.get((slide, 'sensitive')) == 0
           and [c[2:] for c in m.calls if c[0] == 'slide_menu'] == [(O['CF_VIEW_W'], O['ART_SIZE'])],
           'the flat fallback is a stock slide_menu with one image per album, insensitive (the touch layer drives it)')
    m.props[(slide, 'value')] = 0
    m.touch('down', 200, t=1000); m.touch('move', 150, t=1300); m.touch('move', 100, t=1600); m.touch('up', 100, t=1900)
    m.settle()
    expect(any(c[0] == 'widget_set_prop_int' and c[1] == slide and c[2] == 'xoffset' for c in m.calls)
           and ('slide_menu_set_value', 1) in m.calls and m.props.get((slide, 'xoffset')) == 0,
           'a drag in the flat fallback moves and commits the stock slide_menu')
    event = m.alloc(0x40); m.u.mem_write(event, bytes(0x40))
    m.setword(event + O['EVENT_PAINT_CANVAS'], 0x22220000)
    m.call(PSYMS['on_paint'], a0=0, a1=event, count=2000000)
    expect('canvas_draw_image' not in m.names(), 'without a frame, paint draws nothing')

    # 22. Back from the album page with another list loaded: the stock queries run again on the next
    #     tap (see 10), so the row that is opened is the album under the cover whatever was loaded.
    m = cover_machine(albums=2)
    m.call(cover_open, count=5000000)
    m.tap(O['CF_CX'])
    m.setword(pod.DATA['PDEQ_SHOWLIST'][0], m.new_deque([m.record(name='other.flac')]))
    m.tap(O['CF_CX'])
    expect(m.deques[m.opened_album[2]] == m.showlist, 'a replaced list is queried again before the page opens')

    # 23. Hit testing by demo's own widget_find_target (see stock_target): where does a touch in
    #     the middle of the covers go? Hidden widgets must be insensitive (a hidden, sensitive,
    #     full-height tracks view once swallowed every touch: navbar fine, covers dead), so it
    #     reaches the touch layer.
    asset = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_cover.bin')
    m = cover_machine(albums=3)
    m.call(cover_open, count=5000000)
    fy = CF_FRAME_Y   # the frame's top in the window
    for x, y in ((160, fy + 66), (20, fy + 16), (300, fy + 166), (160, fy + 2), (160, fy + O['CF_VIEW_H'] - 2)):
        got = stock_target(m, cover_page_tree(m, asset), x, y)
        expect(got[-1] == 'touch_layer', f'a touch at ({x},{y}) reaches the touch layer ({got})')
    got = stock_target(m, cover_page_tree(m, asset), 40, 25)
    expect(got[-1] == 'btn_return', f'the navbar Back button still gets its touches ({got})')
    for y in (CF_ALBUM_Y + 10, CF_ARTIST_Y + 2):   # the captions over the frame's bottom rows
        got = stock_target(m, cover_page_tree(m, asset), 160, y)
        expect(got[-1] == 'touch_layer', f'a touch on a caption reaches the covers (insensitive captions) ({got})')
    got = stock_target(m, cover_page_tree(m, asset), 160, CF_FRAME_Y + O['CF_VIEW_H'] + 10)
    expect(got == ['m1plus_cover_page'], f'below the frame the artist line takes nothing ({got})')
    # and while the cache builds, only Cancel and the navbar take touches
    m = cover_machine(albums=2, cached=False)
    m.call(cover_open, count=5000000)
    got = stock_target(m, cover_page_tree(m, asset, runtime=False), 160, 283)
    expect(got[-1] == 'btn_cancel', f'Cancel gets its touch while preparing ({got})')
    got = stock_target(m, cover_page_tree(m, asset, runtime=False), 160, 150)
    expect(got[-1] not in ('btn_cancel',), f'nothing hidden takes a touch while preparing ({got})')


    # 26. The page has no hint line; the block of frame and captions sits centred in the 400 px
    #     under the navbar, the captions are scrolling hscroll_labels inside the screen.
    tree = awtk_ui.parse(open(asset, 'rb').read())
    expect('label_hint' not in [w.name for w in tree.walk()], 'the cover page has no hint label')
    m = cover_machine(albums=3); m.call(cover_open, count=5000000)
    expect(('widget_lookup', 'label_hint') not in m.calls, 'the payload looks no hint up')
    frame, art = node(asset_tree(asset), 'view_covers'), CF_FRAME_Y + O['CF_TOP']
    top_gap, bottom_gap = art - 50, CLIENT_H - (CF_ARTIST_Y + CF_ARTIST_H)
    expect(frame.y == CF_FRAME_Y and abs(top_gap - bottom_gap) <= 4,
           f'the covers and captions are centred under the navbar ({top_gap} above, {bottom_gap} below)')
    expect(CF_ALBUM_Y >= frame.y + O['CF_TOP'] + O['ART_SIZE'] + O['CF_REFLECT'],
           'the captions start below the reflections, in the always-black rows of the frame')
    caps = [w for w in tree.walk() if w.name in ('label_album', 'label_artist')]
    expect(len(caps) == 2 and all(w.get('sensitive') == 'false' and w.get('visible') != 'false' for w in caps),
           'the captions are shown but insensitive in the asset')
    expect(not any(c[0] == 'widget_set_sensitive' and c[1] in (m.widgets['label_album'], m.widgets['label_artist'])
                   for c in m.calls), 'the payload never makes the captions sensitive')
    for w in caps:
        ok_props = all(w.get(k) == v for k, v in (('yoyo', 'true'), ('loop', 'true'), ('ellipses', 'true'),
                                                  ('lull', pod_ui.CAPTION_LULL)))
        ok_style = all(w.get(f'style:{st}:text_align_h') == 'center' for st in ('normal', 'disable', 'focused'))
        expect(w.type == 'hscroll_label' and ok_props and ok_style and w.get('only_focus') is None
               and w.get('only_parent_focus') is None,
               f'{w.name} is a centred hscroll_label that loops a long text back and forth ({w.props})')
        expect(w.x >= 12 and w.x + w.w <= 320 - 12, f'{w.name} keeps side margins ({w.x}..{w.x + w.w})')
    expect((frame.w, frame.h) == (O['CF_VIEW_W'], O['CF_VIEW_H']) == (320, pod_ui.COVER_FRAME_H),
           f'the frame is the larger shelf ({frame.w}x{frame.h})')
    m2 = cover_machine(albums=3); m2.call(cover_open, count=5000000)
    tl = [c for c in m2.calls if c[0] == 'view']
    expect(tl and tl[0][2:] == (O['CF_VIEW_W'], O['CF_VIEW_H']), f'the touch layer is the frame size ({tl[:1]})')

    landscape_tests(ctx, asset)


# Gestures (docs/architecture.md section 4, Touch): the reproducers of the V2.1kE touch investigation, each of which
# failed on the earlier on_pointer (12 px dead zone then a jump, release travel ignored, a release far away taken for a
# tap, a press during the snap leaving the shelf between covers, remaining / 3 easing stretched by late callbacks).
def signed(v): return struct.unpack('<i', struct.pack('<I', v & 0xffffffff))[0]


def xoff(m): return signed(shelf_off(m))


def snap_ms(dist, h):
    return min(O['SNAP_MAX_MS'], O['SNAP_BASE_MS'] + O['SNAP_ALBUM_MS'] * abs(dist) // h)


def eased(frm, to, el, ms):
    """patch/coverflow.c eased(): 1 - (1 - p)^3 of the way, in its fixed point."""
    if el >= ms: return to
    q = 256 - el * 256 // ms
    e = 4096 - (q * q * q >> 12)
    d = (to - frm) * e
    return frm + (abs(d) // 4096) * (1 if d >= 0 else -1)   # C division truncates towards zero


def gesture_tests(ctx):
    expect = ctx.expect
    h, cx, slop, start, dpx = O['CF_VIEW_H'], O['CF_CX'], O['TAP_SLOP'], O['DRAG_START'], O['DRAG_PX']
    opened = lambda m: 'navigator_to_with_context' in m.names()
    values = lambda m: [c[1] for c in m.calls if c[0] == 'set_value']

    def page(albums=5, value=0):
        m = cover_machine(albums=albums); m.call(PSYMS['coverflow_open'], count=5000000)
        put_value(m, value)
        return m

    # G1. The drag starts at DRAG_START px and follows the finger from there: no dead zone, no catch-up jump.
    m = page()
    m.touch('down', 200, t=1000)
    m.touch('move', 200 - (start - 1), t=1010); before = xoff(m)
    offs = []
    for i, x in enumerate(range(200 - start, 200 - 40, -1)):
        m.touch('move', x, t=1020 + 10 * i); offs.append(xoff(m))
    expect(before == 0 and offs[0] == 0 and all(b <= a for a, b in zip(offs, offs[1:])) and offs[-1] < 0,
           f'below DRAG_START nothing moves; from it the shelf follows, monotonic ({before}, {offs[:4]}..{offs[-1]})')
    jumps = [a - b for a, b in zip(offs, offs[1:])]
    expect(max(jumps) <= h // dpx + 1, f'a pixel of finger is at most a pixel\'s worth of shelf, no jump at the threshold ({max(jumps)})')
    m = page()
    m.touch('down', cx, t=1000); m.touch('move', cx - (start + 3), t=1030); m.touch('up', cx - (start + 3), t=1300); m.settle()
    expect(start + 3 <= slop and not opened(m) and xoff(m) == 0,
           'once a drag has started the release opens nothing, though still within the tap tolerance; it settles back')

    # G2. A release far from the press with no MOVE in between is a drag, not a tap.
    m = page()
    m.touch('down', 200, t=1000); m.touch('up', 100, t=1300); m.settle()
    expect(not opened(m) and 1 in values(m), f'DOWN at 200, UP at 100, no MOVE: no album opens, the shelf moves on one ({values(m)})')

    # G3. The release's own travel counts (sparse MOVE events): 40 px by the last MOVE, 80 px by the release.
    m = page()
    m.touch('down', 200, t=1000); m.touch('move', 160, t=1100); m.touch('up', 120, t=1500); m.settle()
    expect(values(m) == [1], f'the final 40 px of the release are not lost: past half a cover, the next album ({values(m)})')

    # G4. Vertical and diagonal motion: no tap (beyond the tolerance), no shelf motion, no fling.
    for path in (((160, 150), (163, 170), (163, 190)), ((160, 150), (168, 165), (170, 175)), ((160, 100), (165, 250))):
        m = page()
        m.touch('down', path[0][0], path[0][1], t=1000)
        for i, (x, y) in enumerate(path[1:-1]): m.touch('move', x, y, t=1010 + 10 * i)
        m.touch('up', path[-1][0], path[-1][1], t=1030); m.settle()
        expect(not opened(m) and xoff(m) == 0 and not any(v != 0 for v in values(m)),
               f'a mostly vertical gesture {path} opens nothing and moves nothing ({values(m)})')

    # G5. A tap may wobble: within the tolerance across and under DRAG_START along, it opens the centre album.
    for dx, dy in ((0, 0), (start - 1, 0), (2, slop), (-(start - 1), -slop)):
        m = page()
        m.touch('down', cx, 150, t=1000); m.touch('move', cx + dx, 150 + dy, t=1030); m.touch('up', cx + dx, 150 + dy, t=1060)
        expect(opened(m), f'a tap that wobbles ({dx}, {dy}) still opens the centre album')
    m = page()
    m.touch('down', cx, 150, t=1000); m.touch('up', cx, 150 + slop + 1, t=1060)
    expect(not opened(m), 'a release just past the tolerance (across) is not a tap')

    # G6. Interrupt and tap: a press during the snap stops the shelf where it is and the release settles it on the
    #     nearest cover (no album opens from a moving shelf); a nonzero offset never stays without its timer.
    m = page()
    m.tap(cx + 100); m.clock += 16; m.call(PSYMS['on_snap'], count=2000000)
    mid = xoff(m)
    m.touch('down', cx, t=5000)
    expect(mid != 0 and xoff(m) == mid and any(c[0] == 'timer_remove' for c in m.calls), f'the press stops the animation where it was ({mid})')
    m.touch('up', cx, t=5050)
    expect(not opened(m) and (xoff(m) == 0 or any(c[0] == 'timer_add' for c in m.calls)),
           f'the release opens nothing and settles (offset {xoff(m)}, a timer running)')
    m.settle()
    expect(xoff(m) == 0 and values(m) == ([1] if abs(mid) > h // 2 else []), f'it settles on the nearest cover ({mid} -> {values(m)})')
    m.tap(cx)
    expect(opened(m), 'and the next centre tap opens the album')

    # G7. Interrupt and drag: the drag carries on from where the animation was, no jump to the committed cover.
    m = page()
    m.tap(cx + 100); m.clock += 16; m.call(PSYMS['on_snap'], count=2000000); mid = xoff(m)
    m.touch('down', 200, t=6000); m.touch('move', 200 + start, t=6010); first = xoff(m)
    m.touch('move', 200 + start + 60, t=6200); m.touch('up', 200 + start + 60, t=6600)
    expect(first == mid, f'the drag starts from the interrupted position ({mid} -> {first})')
    m.settle()
    expect(xoff(m) == 0 and not opened(m), 'and settles from where it was let go')

    # G8. No timer: the shelf is not left between covers, the snap finishes at once.
    m = page(); m.timer_fail = True
    m.tap(cx + 100)
    expect(xoff(m) == 0 and 1 in values(m), f'a refused timer commits the side tap at once ({values(m)})')
    m = page()
    m.tap(cx + 100); m.timer_fail = True; m.clock += 16; m.call(PSYMS['on_snap'], count=2000000)
    expect(xoff(m) == 0 and 1 in values(m), 'a timer refused mid-animation commits it too')

    # G9. Elapsed-time easing: irregular callback times give the eased position for the time that has passed,
    #     the animation ends exactly on the target when its time is up, whatever the callbacks did.
    m = page(); m.clock = 50000
    m.tap(cx + 100)
    ms = snap_ms(h, h)
    expect(160 <= ms <= 200, f'a one-album snap lasts {ms} ms')
    seen = []
    for el in (3, 40, 41, 97, ms - 30):
        m.clock = 50000 + el; m.call(PSYMS['on_snap'], count=2000000)
        seen.append((el, xoff(m), eased(0, -h, el, ms), values(m)))
    expect(all(got == want and not v for _, got, want, v in seen), f'the eased offset at each elapsed time, not yet committed ({seen})')
    m.clock = 50000 + ms + 250; m.call(PSYMS['on_snap'], count=2000000)
    expect(xoff(m) == 0 and values(m) == [1] and not any(c[0] == 'timer_add' for c in m.calls),
           'a late callback past the end lands exactly on the target and stops the timer')
    m = page(); m.clock = 70000
    m.tap(cx + 100); m.clock = 70000 + 1000; m.call(PSYMS['on_snap'], count=2000000)
    expect(values(m) == [1], 'one callback a second late finishes the whole animation (it is not stretched)')

    # G10. The fling: a quick flick coasts; a hold before the release does not.
    m = page()
    m.touch('down', 250, t=1000); m.touch('move', 200, t=1020); m.touch('move', 150, t=1040); m.touch('up', 150, t=1050); m.settle()
    expect(values(m) and values(m)[-1] == 3, f'a flick of 100 px in 50 ms coasts to the third album ({values(m)})')
    m = page()
    m.touch('down', 250, t=1000); m.touch('move', 150, t=1050); m.touch('up', 150, t=1400); m.settle()
    expect(values(m) == [1], f'the same travel held still before the release coasts nowhere ({values(m)})')

    # B. The shelf has ends (every shelf, main and per artist, one bounded path): no wrap, a rubber band past the end
    #    (half speed, saturating at OVER_NUM / OVER_DEN of a cover) and the eased snap springing back; flings stop at the ends.
    cap = h * O['OVER_NUM'] // O['OVER_DEN']
    for albums, value, sign, name in ((5, 0, +1, 'the first album'), (5, 4, -1, 'the last album'), (1, 0, +1, 'a one-album shelf (right)'), (1, 0, -1, 'a one-album shelf (left)')):
        m = page(albums, value)
        x0 = 100 if sign > 0 else 260
        m.touch('down', x0, t=1000)
        seen = []
        for i, dx in enumerate((10, 30, 60, 110, 180, 260)):   # the finger goes on and on in the same direction
            m.touch('move', x0 + sign * dx, t=1020 + 20 * i); seen.append(sign * xoff(m))
        raw = lambda dx: (dx - start) * h // dpx
        expect(all(a < b for a, b in zip(seen, seen[1:])) and seen[0] > 0 and max(seen) <= cap and seen[-1] > cap // 2
               and seen[2] < raw(60) // 2 and seen[-1] < raw(260) // 4,
               f'{name}: the shelf stretches past the end at half speed or less, rising and saturating under {cap} ({seen})')
        expect(not values(m) and shelf_value(m) == value, f'{name}: nothing wraps while it is stretched')
        mid = xoff(m)
        m.touch('up', x0 + sign * 260, t=1200)
        m.settle()
        path = [signed(c[1]) for c in m.calls if c[0] == 'set_offset']
        expect(xoff(m) == 0 and shelf_value(m) == value and not values(m) and abs(mid) > 0,
               f'{name}: the release springs back to the end cover and wraps nowhere ({values(m)})')
        expect(path[-1] == 0 and all(abs(a) >= abs(b) for a, b in zip(path, path[1:])) and abs(path[0]) <= abs(mid),
               f'{name}: the spring-back is the eased snap: the offset only falls to 0 ({path[:4]}..)')
    # a fling past the end stops at it, either way; a shelf walked to its end and flicked on never wraps
    m = page(5, 3)
    m.touch('down', 250, t=1000); m.touch('move', 200, t=1020); m.touch('move', 150, t=1040); m.touch('up', 150, t=1050); m.settle()
    expect(shelf_value(m) == 4 and values(m) and max(values(m)) == 4 and 0 not in values(m) and xoff(m) == 0,
           f'a flick left from the fourth of five stops on the last album ({values(m)})')
    m = page(5, 1)
    m.touch('down', 100, t=1000); m.touch('move', 150, t=1020); m.touch('move', 200, t=1040); m.touch('up', 200, t=1050); m.settle()
    expect(shelf_value(m) == 0 and 4 not in values(m) and xoff(m) == 0, f'a flick right from the second album stops on the first ({values(m)})')
    m = page(5, 4)
    for k in range(3):
        m.touch('down', 250, t=2000 + 400 * k); m.touch('move', 200, t=2020 + 400 * k); m.touch('move', 150, t=2040 + 400 * k)
        m.touch('up', 150, t=2050 + 400 * k); m.settle()
    expect(shelf_value(m) == 4 and not values(m), 'three flicks on from the last album: it stays the last, nothing wraps to the first')
    m = page(5, 0)
    m.tap(cx - 100); m.settle()
    expect(shelf_value(m) == 0 and not values(m), 'a tap on the (absent) cover left of the first album brings nothing in')
    m = page(5, 3)
    m.tap(cx + 100); m.settle()
    expect(shelf_value(m) == 4, 'a tap on a side cover still brings it in (the last album)')
    # a press that finds the shelf stretched takes it from where it is (no jump), and its release springs back
    m = page(5, 0)
    m.touch('down', 100, t=1000); m.touch('move', 200, t=1050); m.touch('up', 200, t=1100)   # released stretched: the snap is running
    stretched = xoff(m)
    m.touch('down', 200, t=1110)
    expect(stretched > 0 and xoff(m) == stretched, f'a press during the spring-back stops it where it is ({stretched}, {xoff(m)})')
    m.touch('move', 200 + start + 2, t=1130)
    expect(abs(xoff(m) - stretched) <= 2 * h // dpx + 2, f'and the drag carries on from there without a jump ({stretched} -> {xoff(m)})')
    m.touch('up', 200 + start + 2, t=1400); m.settle()
    expect(xoff(m) == 0 and shelf_value(m) == 0 and not values(m), 'its release springs back to the first album')
    # a drag inside the shelf is unchanged: no rubber band between the ends
    m = page(5, 2)
    m.touch('down', 200, t=1000); m.touch('move', 150, t=1020)
    expect(xoff(m) == -((200 - 150 - start) * h // dpx), f'between the ends the shelf follows the finger one to one ({xoff(m)})')


# The shelf and its textures (docs/architecture.md section 4, Covers / Textures): depth mode owns its position (the
# stock slide_menu laid out every child, up to 4000, on each offset change: slide_menu_set_prop 0x613c94 ->
# widget_layout_children), and paint draws from resident textures only, a page timer decoding what is missing.
def coloured(m, albums):
    """Every album's cache file decodable, album i a flat colour of its own (RGBA bytes)."""
    m.load_image = 0
    cols = []
    for i, p in enumerate(cache_paths(m, albums)):
        c = (20 + 11 * i % 230, 200 - 7 * i % 190, 60 + 13 * i % 190)
        m.images['file://' + p] = (O['ART_SIZE'], O['ART_SIZE'], bytes(c + (255,)) * (O['ART_SIZE'] ** 2))
        cols.append(c)
    return cols


def loaded(m, albums):
    """The albums whose cache file the last call decoded, in order."""
    paths = {('file://' + p): i for i, p in enumerate(cache_paths(m, albums))}
    return [paths[c[1]] for c in m.calls if c[0] == 'widget_load_image' and c[1] in paths]


def centre_px(m):
    b, data, w, h = m.bitmap
    x, y = O['CF_CX'], O['CF_TOP'] + O['ART_SIZE'] // 2
    v = m.word(data + (y * w + x) * 4)
    return v & 255, v >> 8 & 255, v >> 16 & 255


def shelf_tests(ctx):
    expect = ctx.expect
    cx = O['CF_CX']
    stock_shelf = ('slide_menu', 'slide_menu_set_value', 'image_create', 'widget_layout_children')

    # S1. Depth mode never drives a stock widget as the shelf moves: a drag, its snap and the commit only change
    #     the payload's own position (set_offset / set_value) and repaint the frame.
    m = cover_machine(albums=5); m.call(PSYMS['coverflow_open'], count=5000000)
    seen = []
    m.touch('down', 200, t=1000); seen += m.calls
    m.touch('move', 150, t=1100); seen += m.calls
    m.touch('move', 90, t=1200); seen += m.calls
    m.touch('up', 90, t=1500); seen += m.calls
    m.settle(); seen += m.calls
    expect(any(c[0] == 'set_offset' for c in seen) and ('set_value', 1) in seen and shelf_value(m) == 1 and shelf_off(m) == 0,
           'the drag moves the payload\'s shelf and commits the next album')
    expect(not any(c[0] in stock_shelf or (c[0] == 'widget_set_prop_int' and c[2] == 'xoffset') for c in seen),
           'and no stock slide_menu is set, laid out or committed on the way')

    # S2. A large library: no widget per album at open, and a drag step costs the same as on a small shelf.
    costs = {}
    for n in (5, 1000):
        m = cover_machine(albums=n).count(); m.call(PSYMS['coverflow_open'], count=80000000)
        expect(not any(c[0] in stock_shelf for c in m.calls), f'{n} albums: no slide_menu, no image per album')
        m.touch('down', 200, t=1000); m.touch('move', 150, t=1100)
        costs[n] = m.icount
    expect(costs[1000] <= costs[5] * 1.2, f'a drag step costs the same with 1000 albums as with 5 ({costs})')
    print(f'  drag step: {costs[5]:,} payload instructions (5 albums), {costs[1000]:,} (1000 albums)')

    # S3. One album: it is the centre, a drag stretches and springs back onto it, a tap opens it.
    m = cover_machine(albums=1); m.call(PSYMS['coverflow_open'], count=5000000)
    m.touch('down', 200, t=1000); m.touch('move', 60, t=1300); m.touch('up', 60, t=1700); m.settle()
    expect(shelf_value(m) == 0 and shelf_off(m) == 0 and not any(c[0] == 'set_value' for c in m.calls), 'a one-album shelf drags back onto its album')
    m.tap(cx)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 0) in m.calls, 'and a tap opens it')

    # S4. Paint never loads: the first frame's covers are decoded when the shelf is built; a jump far along leaves
    #     paint with placeholders and a loader timer, which decodes one cover per callback, nearest first.
    n = 20
    m = cover_machine(albums=n); cols = coloured(m, n)
    m.call(PSYMS['coverflow_open'], count=20000000)
    first = loaded(m, n)
    attempts = [c for c in m.calls if c[0] == 'widget_load_image']
    expect(first == [0] and len(attempts) == 2 and any(c[0] == 'timer_add' and c[1] == PSYMS['on_load'] for c in m.calls),
           f'the open call decodes the placeholder and the centre cover only ({len(attempts)} image loads, was 6) and arms the loader ({first})')
    rest = []
    for _ in range(10):
        m.call(PSYMS['on_load'], count=20000000); rest += loaded(m, n)
        expect(len(loaded(m, n)) <= 1, 'one cover per loader tick')
        if not any(c[0] == 'timer_add' for c in m.calls): break
    expect(rest == [1, 2, 3, 4], f'the loader then brings the ring around it and the next one ahead, one a tick ({rest})')
    paint(m)
    expect(not any(c[0] in ('widget_load_image', 'fopen', 'access') for c in m.calls) and centre_px(m) == cols[0],
           'paint at rest loads nothing and shows the centre album')
    for stretch in (O['CF_VIEW_H'] // 4, O['CF_VIEW_H'] * O['OVER_NUM'] // O['OVER_DEN']):   # stretched past the first album: it stays the centre, nothing wraps in
        put_off(m, stretch); paint(m)
        expect(not any(c[0] == 'widget_load_image' and c[1].endswith(cache_paths(m, n)[n - 1].rsplit('/', 1)[1]) for c in m.calls) and not [a for a in loaded(m, n) if a >= 10],
               f'stretched {stretch} px past the first album the last album is not drawn or decoded')
    put_off(m, 0); paint(m)
    put_value(m, 10)
    paint(m)
    expect(not any(c[0] in ('widget_load_image', 'fopen', 'access') for c in m.calls), 'paint after a jump loads nothing')
    expect(any(c[0] == 'timer_add' and c[1] == PSYMS['on_load'] for c in m.calls) and centre_px(m) == (0x2b, 0x2b, 0x2b),
           'it shows the placeholder and starts the loader')
    order, rounds = [], 0
    while rounds < 20:
        m.call(PSYMS['on_load'], count=20000000); rounds += 1
        order += loaded(m, n)
        assert len(loaded(m, n)) <= 1
        if not any(c[0] == 'timer_add' for c in m.calls): break
    expect(order[0] == 10 and sorted(order) == sorted(range(7, 15)) and rounds == 8,
           f'the loader decodes one cover per callback, the centre first ({order})')
    paint(m)
    expect(centre_px(m) == cols[10] and not any(c[0] in ('widget_load_image', 'timer_add') for c in m.calls),
           'then paint shows the album, with nothing left to load')

    # S5. Prefetch follows the travel and the cover left behind survives a reversal.
    def step(m, v):
        put_value(m, v); paint(m)
        got = []
        for _ in range(20):
            m.call(PSYMS['on_load'], count=20000000); got += loaded(m, n)
            if not any(c[0] == 'timer_add' for c in m.calls): break
        return got
    m = cover_machine(albums=n); coloured(m, n); put_value(m, 0)
    m.call(PSYMS['coverflow_open'], count=20000000); step(m, 0); paint(m)
    expect(step(m, 1) == [5] and step(m, 2) == [6], 'moving on, the loader fetches only the next cover ahead (5, then 6)')
    back = step(m, 1)
    expect(back == [], f'moving back needs no visible cover again and nothing is wanted past the first album ({back})')


# Landscape (docs/ui.md "Cover Flow landscape"): the same page turned a quarter, drawn into the body under the navbar.
LW, LH, LCX, LY = O['CFL_W'], O['CFL_H'], O['CFL_CX'], O['CFL_Y']
LFILE, LTMP = '/mnt/data/m1plus/coverflow-landscape', '/mnt/data/m1plus/coverflow-landscape.tmp'
LAND_RECT = (0, LY, LH, LW)                      # the landscape frame in the window: the body under the navbar
PORTRAIT_RECT = (0, CF_FRAME_Y, O['CF_VIEW_W'], O['CF_VIEW_H'])
NAV_NAMES = ('navigationbar_view', 'btn_return', 'btn_backtoplayer', 'label_title')


def land_machine(albums=5, saved=None, **kw):
    """A machine opened on Cover Flow with the page's geometry modelled: view_covers at its asset place in the 450 px
    window, every widget_move / widget_resize written to the widget_t too, and the touch layer's parent chain in
    emulated memory for the stock widget_to_local (the window under the 30 px status bar)."""
    m = cover_machine(albums=albums, **kw)
    m.load_image = 0
    m.mem_geometry = True
    cover_rects(m)
    if saved is not None: m.fs[LFILE] = saved
    m.canvas_mem = m.alloc(0x80)
    m.call(PSYMS['coverflow_open'], count=5000000)
    land_parents(m)
    return m


def cached(m, artist, album):
    """The cache file of an album the machine's list was changed to, so the page opens straight on the covers."""
    c = art_file(fnv(fnv(O['FNV_SEED'], artist), album) or 1)
    m.present.add(c); m.files[c] = 4096


def land_parents(m):
    if 'view' in m.widgets:
        win = m.alloc(0x80); m.setword(win + 4, 30)
        covers, inp = m.widgets['view_covers'], m.widgets['view']
        for w in (covers, inp):   # x, y, w, h @0..0xc as the props stand (later moves write them too)
            for i, k in enumerate('xywh'): m.setword(w + 4 * i, m.props.get((w, k), 0))
        m.setword(covers + 0x44, win)
        m.setword(inp + 0x44, covers)


def lt(m, kind, lx, ly, t):
    """A pointer event at the landscape point (lx along the 400 px side, ly across): physical x = CFL_H - 1 - ly,
    screen y = 30 (status bar) + CFL_Y (navbar) + lx."""
    m.touch(kind, LH - 1 - ly, 30 + LY + lx, t)


def ltap(m, lx, ly):
    lt(m, 'down', lx, ly, 1000); calls = list(m.calls)
    lt(m, 'up', lx, ly, 1080); m.calls = calls + m.calls


def bitmaps_made(m): return [(c[1], c[2]) for c in m.calls if c[0] == 'bitmap_create_ex']


def paint_canvas(m):
    event = m.alloc(0x40); m.u.mem_write(event, bytes(0x40))
    m.setword(event + O['EVENT_PAINT_CANVAS'], m.canvas_mem)
    m.call(PSYMS['on_paint'], a0=0, a1=event, count=400000000)


def physical(m, x, y):
    """The pixel at the landscape point (x, y) of the frame the last paint drew."""
    b, data, w, h = m.bitmap
    return struct.unpack('<I', m.u.mem_read(data + (x * LH + LH - 1 - y) * 4, 4))[0]


def landscape_tests(ctx, asset):
    expect = ctx.expect
    drag = O['CFL_DRAG_PX']
    # 27. The Settings page's switch decides the presentation (no navbar button, no handler on the page): nothing saved is
    #     portrait, the 320x276 frame, the covers view and the touch layer at the asset's rectangle; "1" is landscape: the
    #     frame is the 320x400 body under the navbar, the covers view and the touch layer are exactly that rectangle, the
    #     navbar is left alone (Back, title, Now Playing), the caption labels are hidden and stay insensitive. Opening
    #     writes nothing, and the page has no function that changes the presentation once it is open.
    m = land_machine()
    expect(bitmaps_made(m) == [(O['CF_VIEW_W'], O['CF_VIEW_H'])] and m.fs.get(LFILE) is None, 'no saved choice: portrait, the 320x276 frame')
    covers, inp = m.widgets['view_covers'], m.widgets['view']
    expect(abs_rect(m, covers) == abs_rect(m, inp) == PORTRAIT_RECT and O['CF_COVER_Y'] == pod_ui.COVER_Y,
           f'portrait: covers view and touch layer are the frame, at the asset\'s rectangle ({abs_rect(m, inp)})')
    expect(not any(n in PSYMS for n in ('on_rotate', 'set_land')) and 'btn_landscape' not in m.widgets,
           'the page has no rotate handler and binds no landscape button')
    m = land_machine(saved=b'1\n')
    covers, inp = m.widgets['view_covers'], m.widgets['view']
    expect(bitmaps_made(m) == [(LH, LW)] and (LH, LW) == (O['CF_VIEW_W'], CLIENT_H - O['NAV_H']),
           f'saved landscape: the frame of the 320x400 body ({bitmaps_made(m)})')
    expect(abs_rect(m, covers) == abs_rect(m, inp) == LAND_RECT and m.bitmap[2:] == LAND_RECT[2:],
           f'the covers view, the touch layer and the frame bitmap are one rectangle, the body ({abs_rect(m, inp)}, {m.bitmap[2:]})')
    expect(LAND_RECT[1] >= O['NAV_H'] and LAND_RECT[1] + LAND_RECT[3] == CLIENT_H, 'under the navbar, to the window\'s bottom: nothing overlaps the navbar')
    expect(not any(c[0] in ('widget_set_visible', 'widget_set_sensitive') and c[1] in [m.widgets[n] for n in NAV_NAMES]
                   for c in m.calls), 'the navbar and its buttons are left as they are (Back, title, Now Playing)')
    caps = (m.widgets['label_album'], m.widgets['label_artist'])
    expect(all(('widget_set_visible', w, 0) in m.calls for w in caps)
           and not any(c[0] == 'widget_set_sensitive' and c[1] in caps for c in m.calls), 'the caption labels are hidden, never made sensitive')
    expect(not any(c[0] in ('write', 'rename') for c in m.calls) and m.fs.get(LFILE) == b'1\n', 'opening writes nothing')

    # 27b. Repaint (the V2.1lF failure: only the slide_menu's 320x276 was ever marked dirty, so on the device only the
    #      first 276 of the 450 px landscape frame changed, "the left 60 %"). Whatever moves the shelf or changes its
    #      album marks the whole frame, in both presentations (since V2.1lJ depth mode has no slide_menu at all).
    for saved, rect in ((b'1\n', LAND_RECT), (b'0\n', PORTRAIT_RECT)):
        m = land_machine(albums=5, saved=saved)
        put_value(m, 1)
        name = 'landscape' if saved == b'1\n' else 'portrait'
        go = (lambda k, a, t: lt(m, k, a, 150, t)) if saved == b'1\n' else (lambda k, a, t: m.touch(k, a, CF_FRAME_Y + 30 + 100, t))
        go('down', 300, 1000)
        go('move', 250, 1300)
        expect(covered(dirty_rects(m), rect), f'{name}: a drag step marks the whole frame {rect} ({dirty_rects(m)})')
        go('up', 250, 1600)
        steps = []
        for _ in range(200):   # the snap animation, one timer step at a time
            m.clock += 16; m.call(PSYMS['on_snap'], count=2000000)
            if any(c[0] == 'set_offset' for c in m.calls): steps.append(covered(dirty_rects(m), rect))
            if not any(c[0] == 'timer_add' for c in m.calls): break
        expect(steps and all(steps), f'{name}: every snap step marks the whole frame ({len(steps)} steps)')
        put_value(m, 3)
        m.call(PSYMS['on_changed'], count=2000000)
        expect(covered(dirty_rects(m), rect), f'{name}: an album change (the captions) marks the whole frame')
        if saved == b'1\n':
            expect('slide_menu' not in m.widgets, 'no stock widget of the size of the portrait frame is involved')

    # 28. Persistence: the saved choice opens the page that way, with no write; anything else is portrait.
    for data, want in ((b'1\n', True), (b'0\n', False), (b'x', False), (b'', False), (b'1x', False), (b'11', False)):
        m = land_machine(saved=data)
        expect(bitmaps_made(m) == ([(LH, LW)] if want else [(O['CF_VIEW_W'], O['CF_VIEW_H'])]),
               f'saved {data!r}: opens {"landscape" if want else "portrait"} ({bitmaps_made(m)})')
        expect(not any(c[0] == 'write' for c in m.calls) and m.fs.get(LFILE) == data, 'opening writes nothing')
        expect((abs_rect(m, m.widgets['view']) == LAND_RECT) == want, 'the layout follows')
    m = cover_machine(albums=3); m.fs[LFILE] = b'1\n'; m.bitmap_ok = False
    m.call(PSYMS['coverflow_open'], count=5000000)
    expect(not any(c[0] == 'widget_move' for c in m.calls), 'no depth frame (flat covers): no landscape, whatever was saved')

    # 29. Touch in landscape: the carousel runs along the 400 px side (physical y, under the navbar).
    m = land_machine(albums=5, saved=b'1\n')
    put_value(m, 1)
    lt(m, 'down', 300, 150, 1000); lt(m, 'move', 300 - drag // 2, 150, 1300)
    mid = struct.unpack('<i', struct.pack('<I', shelf_off(m) & 0xffffffff))[0]
    lt(m, 'move', 300 - drag - 10, 150, 1600); lt(m, 'up', 300 - drag - 10, 150, 1900); m.settle()
    want = -((drag // 2 - O['DRAG_START']) * O['CF_VIEW_H'] // drag)
    expect(abs(mid - want) <= 1, f'finger travel along the long side past the drag threshold moves the shelf by as much (xoffset {mid}, want {want})')
    expect(('set_value', 2) in m.calls and 'navigator_to_with_context' not in m.names(),
           'a leftward drag on the long side moves on to the next album, and opens nothing')
    put_value(m, 1)
    lt(m, 'down', 100, 150, 3000); lt(m, 'move', 100 + drag // 2, 150, 3300); lt(m, 'move', 100 + drag + 10, 150, 3600)
    lt(m, 'up', 100 + drag + 10, 150, 3900); m.settle()
    expect(('set_value', 0) in m.calls, 'a drag to the right goes back an album')
    put_value(m, 1)
    lt(m, 'down', LCX, 60, 5000); lt(m, 'move', LCX, 160, 5200); lt(m, 'move', LCX, 260, 5400); lt(m, 'up', LCX, 260, 5600); m.settle()
    expect(shelf_off(m) == 0 and not any(c[0] == 'set_value' for c in m.calls)
           and 'navigator_to_with_context' not in m.names(), 'a drag across the short side moves nothing')
    put_value(m, 1)
    lt(m, 'down', 380, 150, 7000); lt(m, 'move', 330, 150, 7005); lt(m, 'move', 280, 150, 7010); lt(m, 'up', 280, 150, 7012); m.settle()
    offs = [c[1] for c in m.calls if c[0] == 'set_offset']
    expect(max(abs(o) for o in offs) > 2 * O['CF_VIEW_H'], 'a flick along the long side coasts on')
    put_value(m, 1)
    lt(m, 'down', 200, 90, 9000); lt(m, 'move', 190, 90, 9100); lt(m, 'abort', 190, 90, 9150)
    expect(any(c[0] == 'widget_ungrab' for c in m.calls), 'an abort releases the grab'); m.settle()
    expect(shelf_off(m) == 0, 'and snaps back')
    put_value(m, 2)
    m.call(PSYMS['on_changed'], count=2000000)
    ltap(m, LCX, 150)
    expect(('navigator_to_with_context', 'albuminfo_page', O['CLASS_ALBUMS'], 2) in m.calls
           and ('batchadd_albumcover_task', 0, 0) in m.calls, 'a tap on the centre cover opens that album (the cover thread is released too)')
    expect(('loadAlbumList', O['CLASS_ALBUMS'], 0, '') in m.calls and ('albumcoverinfo_init', m.opened_album[2]) in m.calls,
           'by the stock path, as in portrait')
    ltap(m, LCX + 120, 150)   # right of the centre: the first side cover (drawn about 120 px out)
    expect('navigator_to_with_context' not in m.names(), 'a side cover opens nothing')
    m.settle()
    expect(('set_value', 3) in m.calls, 'a tap to the right of the centre brings the next album in')
    put_value(m, 2)
    ltap(m, LCX - 120, 150); m.settle()
    expect(('set_value', 1) in m.calls, 'a tap to the left brings the previous album in')
    put_value(m, 2)
    ltap(m, LW - 5, 150); m.settle()
    expect(('set_value', 4) in m.calls, 'a tap on the second cover out brings that one in, two albums over')
    put_value(m, 2)
    ltap(m, LCX + 20, 150)
    expect('navigator_to_with_context' in m.names(), 'a tap within half a cover of the centre line still opens')
    m = land_machine(saved=b'1\n')
    put_value(m, 2)
    ltap(m, 20, 20); m.settle()   # the logical top-left corner (V2.1lF drew an exit control there, over the covers)
    expect(not any(c[0] == 'bitmap_create_ex' for c in m.calls) and m.fs.get(LFILE) == b'1\n'
           and any(c[0] == 'set_value' and c[1] in (0, 1) for c in m.calls),
           'the frame has no control of its own: a corner tap is a cover tap')

    # 30. Paint in landscape: the covers are the host renderer's turned frame, the captions drawn into it, the whole
    #     frame blitted over the touch layer, which is exactly the frame's rectangle in the window.
    m = land_machine(albums=5, saved=b'1\n').count()
    put_value(m, 2); put_off(m, O['CF_VIEW_H'] // 4)
    m.call(PSYMS['on_changed'], count=2000000)
    m.glyphs.clear(); paint_canvas(m)
    land_icount = m.icount
    expect(('canvas_draw_image', m.bitmap[0]) in m.calls and m.bitmap[2:] == (LH, LW), 'the body-sized frame is drawn on the canvas')
    blit = [x for x in m.blits if x[0] == m.bitmap[0]][-1]
    ix, iy, iw, ih = abs_rect(m, m.widgets['view'])
    expect(blit[1] == (0, 0, LH, LW) == blit[2] and (ix, iy + blit[2][1], blit[2][2], blit[2][3]) == LAND_RECT == (ix, iy, iw, ih),
           f'whole, at the touch layer\'s origin, the body\'s rectangle in the window ({blit[1:]}, layer {(ix, iy, iw, ih)})')
    host = host_frame(-((O['CF_VIEW_H'] // 4) * 65536 // O['CF_VIEW_H']), land=True)
    hostpx = lambda x, y: struct.unpack_from('<I', host, (x * LH + LH - 1 - y) * 4)[0]
    under = [(x, y) for y in range(O['CFL_ALBUM_Y'] - 6) for x in range(LW)]
    expect(all(physical(m, x, y) == hostpx(x, y) for x, y in under[::3]),
           'the covers are the host build\'s turned shelf, pixel for pixel, above the captions')
    expect({s for _, s in m.glyphs} == {22, 18}, f'the captions use the labels\' own sizes ({sorted({s for _, s in m.glyphs})})')
    expect(''.join(chr(c) for c, s in m.glyphs if s == 22).startswith('Album 2'), 'the album line is the centre album')
    # "Album 2": 7 glyphs of 8 + 1 px advance centred; the mock's glyph is 6 wide, at x 1, its top (h - 2) above the baseline
    top = O['CFL_ALBUM_Y'] - (22 * 3 // 4 - 2) + (22 - 4)
    x0 = (LW - 7 * 9) // 2
    expect(physical(m, x0 + 1 + 2, top + 3) & 0xffffff == 0xffffff and physical(m, x0 - 20, top + 3) & 0xffffff == 0
           and physical(m, x0 + 1 + 2, top + 3) >> 24 == 255, 'the album line is white at the centred place, nothing beside it, the frame opaque')
    top18, x1 = O['CFL_ARTIST_Y'] - (18 * 3 // 4 - 2) + (18 - 4), (LW - 8 * 9) // 2
    expect(physical(m, x1 + 1 + 2, top18 + 3) & 0xffffff == 0xaaaaaa, 'the artist line is grey, below it')
    print(f'  landscape frame: {land_icount:,} payload instructions ({LW}x{LH} logical, {LH}x{LW} bitmap, {LH * LW * 4 // 1024} KB)')

    # a long name is cut with an ellipsis inside the caption width
    m = cover_machine(albums=2); m.load_image = 0; m.canvas_mem = m.alloc(0x80); m.fs[LFILE] = b'1\n'
    m.showlist[0] = m.record(album='x' * 70, artist='Artist 0', path='/mnt/mmc/m/0/1.flac', rid=1)
    cached(m, 'Artist 0', 'x' * 70)
    m.call(PSYMS['coverflow_open'], count=5000000)
    m.glyphs.clear()
    paint_canvas(m)
    al = [c for c, s in m.glyphs if s == 22]
    fit = (O['CFL_CAP_W'] - 17) // 9   # the mock's 'x' advances 8 + 1 px, its ellipsis 16 + 1
    expect(al[-fit - 2:] == [0x2026] + [ord('x')] * fit + [0x2026],   # the ellipsis measured, then what is drawn
           f'a long album name keeps what fits ({fit} chars) and ends in an ellipsis ({len(al)} glyph calls)')
    lit = [x for x in range(LW) if physical(m, x, top + 3) & 0xffffff]
    expect(lit and (LW - O['CFL_CAP_W']) // 2 <= lit[0] and lit[-1] < (LW + O['CFL_CAP_W']) // 2, f'inside the {O["CFL_CAP_W"]} px width ({lit[0]}..{lit[-1]})')
    # a CJK name (wide glyphs), a missing glyph (a 4 px gap) and an empty artist draw without a fault
    m = cover_machine(albums=2); m.load_image = 0; m.canvas_mem = m.alloc(0x80); m.fs[LFILE] = b'1\n'
    m.showlist[0] = m.record(album='中文标题�结尾', artist='', path='/mnt/mmc/m/0/1.flac', rid=1)
    cached(m, '', '中文标题�结尾')
    m.call(PSYMS['coverflow_open'], count=5000000)
    m.glyphs.clear()
    paint_canvas(m)
    expect([c for c, s in m.glyphs if s == 22].count(0x4e2d) == 2 and not [1 for c, s in m.glyphs if s == 18], 'CJK, a missing glyph and an empty artist line draw')
    # a commit redraws the frame with the new album's caption (the covers did not move)
    m = land_machine(albums=5, saved=b'1\n')
    put_value(m, 0)
    paint_canvas(m); put_value(m, 1)
    m.call(PSYMS['on_changed'], count=2000000)
    m.glyphs.clear(); paint_canvas(m)
    expect(''.join(chr(c) for c, s in m.glyphs if s == 22).startswith('Album 1') and 'canvas_draw_image' in m.names(),
           'a commit redraws the frame with the new album\'s caption')
    m = land_machine(albums=5).count()
    put_value(m, 2); put_off(m, O['CF_VIEW_H'] // 4)
    paint_canvas(m)
    print(f'  portrait frame: {m.icount:,} payload instructions; landscape {land_icount:,} ({land_icount / m.icount:.2f}x)')
    expect(land_icount < 3 * m.icount, 'a landscape frame costs less than three portrait ones')

    # 31. Close in landscape frees the frame; the asset has no landscape button (the title takes its space back);
    #     hit testing on the page as the payload laid it out.
    m = land_machine(saved=b'1\n')
    expect(len(m.bitmaps) == 1, 'one frame bitmap while open')
    m.call(PSYMS['on_destroy'], count=2000000)
    expect(not m.bitmaps and m.destroyed >= 1, 'closing in landscape frees the body-sized frame')
    tree = awtk_ui.parse(open(asset, 'rb').read())
    expect(tree.find('btn_landscape') is None and not [w for w in tree.walk() if 'rotate' in str(w.props)],
           'the navbar has no landscape button (the Settings switch replaced it)')
    lbl = tree.find('label_title')
    settings_lbl = awtk_ui.parse(open(os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_settings.bin'), 'rb').read()).find('label_title')
    expect((lbl.x, lbl.w) == (settings_lbl.x, settings_lbl.w) and lbl.x + lbl.w > O['NAV_VIEW_X'] and [c.name for c in tree.find('navigationbar_view').children] == ['label_title', 'btn_return', 'btn_backtoplayer', 'btn_songs'],
           'the title has the whole navbar between Back and Now Playing, as on the other pages without a toggle')
    imgs = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx')
    expect(not any(os.path.exists(os.path.join(imgs, f'pod_nav_rotate{s}.png')) for s in ('', '_down')), 'the rotate glyph images are no longer in the tree')
    m = land_machine(saved=b'1\n')
    t = cover_page_tree(m, asset)   # the asset with the payload's visibility, sensitivity and geometry
    expect((node(t, 'view_covers').y, node(t, 'touch_layer').h) == (LY, LW), 'the tree is the landscape layout')
    for name in ('btn_return', 'btn_backtoplayer'):   # each navbar button's middle
        b = node(t, name)
        got = stock_target(m, cover_page_tree(m, asset), b.x + b.w // 2, b.y + b.h // 2)
        expect(got[-1] == name, f'in landscape the navbar\'s {name} gets its touches ({got})')
    for x, y in ((160, LY + 2), (160, CF_ALBUM_Y + 4), (160, CF_ARTIST_Y + 4), (10, CLIENT_H - 2), (310, 60)):
        got = stock_target(m, cover_page_tree(m, asset), x, y)
        expect(got[-1] == 'touch_layer', f'a touch at ({x},{y}) in the landscape body reaches the touch layer ({got})')


def missing_only_tests(ctx):
    """Cover Flow's open builds the missing covers only (Rebuild Covers is Home's: test/pod/homecover.py)."""
    expect = ctx.expect
    # The normal open is the missing-only build.
    m = cover_machine(albums=3, cached=False)
    m.call(PSYMS['coverflow_open'], count=5000000)
    expect(build_state(m)['mode'] == 0 and build_state(m)['total'] == 3, 'coverflow_open builds the missing covers only (CC_MISSING)')
    m = cover_machine(albums=3, cached=False)
    cached = cache_paths(m, 3)[1]; m.present.add(cached); m.files[cached] = 0     # a marker counts as cached
    m.call(PSYMS['coverflow_open'], count=5000000)
    expect(build_state(m)['total'] == 2 and [t for t, _ in build_jobs(m)] == ['/mnt/mmc/m/0/1.flac', '/mnt/mmc/m/2/1.flac'], 'a marker or a picture is not rebuilt by the normal open')
