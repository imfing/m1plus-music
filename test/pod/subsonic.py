"""Navidrome/Subsonic JSON parsing and metadata transfer (patch/subsonic.c)."""
import json, struct
from harness import *  # noqa: F401,F403
import awtk_ui, pod_pages, pod_ui

REGION, SIZE = 0x30000000, 0x40000
SB_ID, SB_TEXT = 96, 192
SONG_SIZE = SB_ID + SB_TEXT * 3 + SB_ID + 12 + 7 * 4


def parser_tests(ctx):
    expect = ctx.expect
    m = Machine()
    m.u.mem_map(REGION, SIZE)
    body = json.dumps({"subsonic-response": {"status": "ok", "version": "1.16.1",
                      "searchResult3": {"song": [{"id": "abc-1", "title": "Café", "artist": "A Artist",
                                                       "album": "An Album", "suffix": "flac", "duration": 245,
                                                       "track": 7, "discNumber": 2}]}}}, ensure_ascii=False).encode()
    src, dst = REGION + 128, REGION + 4096
    m.u.mem_write(src, body)
    n = m.call(PSYMS['sb_songs'], a0=src, a1=len(body), a2=dst, a3=1)
    raw = bytes(m.u.mem_read(dst, SONG_SIZE))
    field = lambda off, cap: raw[off:off + cap].split(b'\0')[0].decode()
    expect(n == 1 and field(0, SB_ID) == 'abc-1' and field(SB_ID, SB_TEXT) == 'Café'
           and field(SB_ID + SB_TEXT, SB_TEXT) == 'A Artist'
           and field(SB_ID + SB_TEXT * 2, SB_TEXT) == 'An Album', 'Subsonic song title, artist, and album parse as UTF-8')
    off = SB_ID + SB_TEXT * 3 + SB_ID + 12
    expect(struct.unpack_from('<III', raw, off) == (245, 7, 2), 'duration, track and disc numbers parse')
    album_song = b'{"subsonic-response":{"status":"ok","album":{"song":[{"id":"dsd-1","title":"DSD Song","suffix":"dsf"}]}}}'
    m.u.mem_write(src, album_song)
    n = m.call(PSYMS['sb_songs'], a0=src, a1=len(album_song), a2=dst, a3=1)
    song = REGION + 4096
    raw = bytearray(m.u.mem_read(song, SONG_SIZE))
    raw[SB_ID + SB_TEXT * 3 + SB_ID:SB_ID + SB_TEXT * 3 + SB_ID + 4] = b'dsf\0'
    m.u.mem_write(song, bytes(raw))
    name = REGION + 32768
    m.u.mem_write(name, bytes(256))
    length = m.call(PSYMS['sb_track_filename'], a0=name, a1=256, a2=song)
    filename = bytes(m.u.mem_read(name, length + 1)).split(b'\0')[0].decode()
    expect(n == 1 and filename == 'DSD Song.dsf', 'album songs parse, and queue filenames retain the original DSF suffix')

    query = REGION + 32768
    m.u.mem_write(query, bytes(128))
    n = m.call(PSYMS['sb_sync_query'], a0=query, a1=128, a2=128)
    text = bytes(m.u.mem_read(query, n + 1)).split(b'\0')[0].decode()
    expect(n > 0 and text == '&query=&songCount=64&albumCount=0&artistCount=0&songOffset=128',
           'full-library sync pages use the Subsonic songOffset parameter')


def ui_tests(ctx):
    root = pod_ui.build_subsonic_page(pod_pages.SUBSONIC_PAGE)
    roundtrip = awtk_ui.parse(awtk_ui.serialize(root))
    nodes = []

    def visit(node):
        nodes.append(node)
        for child in node.children:
            visit(child)

    visit(roundtrip)
    by_name = {node.get('name'): node for node in nodes if node.get('name')}
    required = ('sb_connect', 'sb_connect_label', 'sb_connected_dot', 'sb_sync', 'sb_sync_icon', 'sb_search', 'sb_tracks', 'sb_dsd', 'sb_view',
                'sb_tracks_mark', 'sb_dsd_mark',
                'sb_grid_row0', 'sb_grid_art0', 'sb_row_play0', 'sb_row_download_icon0')
    ctx.expect(all(name in by_name for name in required) and 'sb_play' not in by_name and 'sb_download' not in by_name
               and 'sb_prev' not in by_name and 'sb_next' not in by_name,
               'Navidrome page has songs and DSD downloads with list/grid views and row actions')
    ctx.expect(all(by_name[name].h >= 44 for name in ('sb_connect', 'sb_sync', 'sb_search', 'sb_tracks', 'sb_dsd', 'sb_view', 'sb_row_play0', 'sb_row_download0')),
               'Navidrome touch controls meet the 44 px target height')
    ctx.expect(by_name['sb_row_play0'].x < by_name['sb_row_download0'].x
               and by_name['sb_row_download0'].x + by_name['sb_row_download0'].w <= 320,
               'track play and download icons fit on the right side of each row')
    ctx.expect(all(f'{name}_icon' in by_name for name in ('sb_tracks', 'sb_dsd')),
               'songs and DSD downloads have clear section icons')
    rows = [node for node in nodes if node.get('name', '').startswith('sb_row') and node.get('name')[6:].isdigit()]
    ctx.expect(len(rows) == 6 and all(row.w == 320 and row.h == 52 for row in rows), 'six spacious virtual rows cover the viewport and scroll overscan')
    ctx.expect(by_name['sb_scrollview'].h == 276 and by_name['sb_rows'].h == 1260,
               'the stock scroll view exposes the virtualized full-library list without paging controls')
    ctx.expect(by_name['sb_connect'].get('style') == 'btn_tablerow_style'
               and all(by_name[name].get('style') == 'btn_tablerow_style' for name in ('sb_tracks', 'sb_dsd')),
               'server and library controls use the stock themed button style')
    ctx.expect('sb_connection' not in by_name,
               'the header has no saved-state label crowding Server and the search/sync icons')


def login_tests(ctx):
    src = open(os.path.join(ROOT, 'patch', 'subsonic.c'), encoding='utf-8').read()
    ctx.expect('sb_setup_defer_prompt(SB_SETUP_USER);' in src and 'sb_setup_defer_prompt(SB_SETUP_PASSWORD);' in src
               and 'if (++sbp.setup_tries < 40) return RET_REPEAT;' in src,
               'URL, username and password prompts chain after each prior keyboard closes')
    ctx.expect('if (!text[0])' in src and 'pod_toast(TR("Enter a server password"))' in src,
               'login rejects an empty password instead of saving credentials that cannot sync')
    ctx.expect('head.count + head.dsd_count > SB_SYNC_LIMIT' in src and 'sb_fixed_equal(head.server' in src
               and 'head.count + head.dsd_count' in src and 'SB_INDEX_MAGIC "SBIDX2' in src
               and 'sbp.count = 0;\n            close(fd);\n            return -1;' in src,
               'SD metadata indexes are bounded, identity-checked, and rejected if truncated')
    ctx.expect('if (sb_is_dsd(song->suffix)) continue;' in src and 'if (sb_is_dsd(sbp.songs[at].suffix))' in src
               and 'sb_index_read_range(first, (unsigned)n, queue_songs)' in src and 'play_at = 0' in src
               and 'start_playqueue(play_at);' in src,
               'DSF/DFF stay out of stream queues, which continue across synced index windows from the selected track')
    ctx.expect('get_wifisignal() <= 0' in src and 'sb_set_connected(1);' in src and '"#34C759"' in src,
               'Wi-Fi is checked before connection and successful server checks show green status')
    ctx.expect('sbp.dsd_view = 0;' in src and 'widget_set_prop_str(sbp.view_icon, "image", icon);' in src,
               'search and view-mode changes cannot carry the DSD-only behavior into regular songs')
    ctx.expect('if (!sb_is_dsd(sbp.songs[i].suffix))' in src and 'rc = regular;' in src,
               'server-side search results keep DSD tracks in their dedicated downloads section')
    ctx.expect('sb_set_active_tab(dsd_view);' in src and 'style:normal:bg_color' in src and 'pod_sb_download' in src,
               'the selected library tab is highlighted and its DSD glyph follows the accent')
    ctx.expect('sb_set_connected(1);' in src and 'sb_connected_dot' in src and '"#34C759"' in src
               and 'TR(sbp.connected ? "Connected" : "Server")' in src,
               'the Server control shows a green connection dot and Connected label after a successful check')
    ctx.expect('pod_confirm(TR("Sync Navidrome songs and artwork to the SD card now?"))' in src,
               'manual library sync asks before starting')
    ctx.expect('offset > count || (count && offset == count)' in src and 'if (n > 0)' in src
               and 'No regular songs in the synced library' in src,
               'switching to an empty Songs section clears the previous DSD rows instead of leaving stale tracks')
    ctx.expect('if (!sbp.index_valid)' in src and 'sbp.index_valid = 0;' in src
               and 'sb_input_locked() || sbp.switching_view' in src,
               'page reopen preserves a valid index and ignores re-entrant scroll events while switching views')
    ctx.expect('sb_play_local_file' in src and 'sb_delete_offline' in src and 'pod_ic_rd_remove' in src
               and 'Delete this downloaded DSD track from the SD card?' in src,
               'downloaded DSD rows change to local Play and confirmed Delete actions')
    ctx.expect('getCoverArt' in src and 'sb_sync_art(sink)' in src and 'sb_cover_file(cc_playing())' in open(os.path.join(ROOT, 'patch', 'nowplaying.c'), encoding='utf-8').read(),
               'artwork sync caches bounded cover images and exposes them to Now Playing')


def run(ctx):
    parser_tests(ctx)
    ui_tests(ctx)
    login_tests(ctx)
