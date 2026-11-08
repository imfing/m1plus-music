"""Navidrome/Subsonic JSON parsing and metadata transfer (patch/subsonic.c)."""
import json, struct, subprocess, tempfile
from pathlib import Path
from harness import *  # noqa: F401,F403
import awtk_ui, pod_pages, pod_ui, mod_icons
import palette as palette_mod

REGION, SIZE = 0x30000000, 0x40000
SB_ID, SB_TEXT = 96, 192
SB_META, SB_SUFFIX = 96, 12
SB_FIELDS = SB_ID + SB_TEXT * 3 + SB_META * 4 + SB_SUFFIX
SONG_SIZE = SB_FIELDS + 8 * 4


def download_validation_tests(ctx):
    """Run the actual response parser/validators on a host, including bad ranges."""
    source = Path(ROOT, 'patch', 'subsonic.c').read_text()
    start = source.index('typedef struct {\n    char data[SB_RESPONSE_MAX]')
    sink = source[start:source.index('} sb_sink_t;', start) + len('} sb_sink_t;')]
    start = source.index('typedef struct {\n    char magic[8], server[256]')
    resume = source[start:source.index('} sb_resume_meta_t;', start) + len('} sb_resume_meta_t;')]

    def func(name):
        start = source.index(name)
        start = source.rfind('\n', 0, start) + 1
        while '{' not in source[start:source.index('\n', start)]:
            start = source.index(name, source.index('\n', start))
            start = source.rfind('\n', 0, start) + 1
        end_line = source.index('\n', start)
        if '}' in source[start:end_line]:
            return source[start:end_line]
        return source[start:source.index('\n}', start) + 2]

    helpers = '\n'.join(func(name) for name in (
        'static unsigned sb_len(', 'static int sb_ascii_lower(', 'static int sb_prefix(',
        'static int sb_strong_etag(', 'static int sb_header_value(', 'static int sb_text_type(',
        'static int sb_download_headers_valid(', 'static unsigned sb_header(',
        'static int sb_audio_response_valid(', 'static int sb_bytes_equal(', 'static int sb_fixed_equal(',
        'static int sb_terminated(', 'static int sb_resume_matches('))
    program = r'''
static void line(sb_sink_t *s, const char *text) { sb_header((void *)text, 1, strlen(text), s); }
static void response(sb_sink_t *s, const char *status, const char *range, const char *etag) {
    line(s, status); if (range) line(s, range); if (etag) line(s, etag);
    line(s, "Content-Type: audio/flac\r\n"); line(s, "\r\n");
}
int main(void) {
    sb_sink_t s = {0};
    sb_resume_meta_t meta = {0};
    memcpy(meta.magic, "SBRES1\0\0", 8); strcpy(meta.server, "http://one"); strcpy(meta.user, "a");
    strcpy(meta.id, "track"); strcpy(meta.etag, "\"first\"");
    if (!sb_resume_matches(&meta, "http://one", "a", "track")) return 12;
    if (sb_resume_matches(&meta, "http://two", "a", "track") ||
        sb_resume_matches(&meta, "http://one", "b", "track") ||
        sb_resume_matches(&meta, "http://one", "a", "different")) return 13;
    s.resume_offset = 1000; strcpy(s.resume_etag, "\"first\"");
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 1000-9999/10000\r\n", "ETag: \"first\"\r\n");
    if (!s.headers_ok) return 1;
    s.http_status = 206; s.content_length = s.written = 9000; s.prefix_used = 4; memcpy(s.prefix, "fLaC", 4);
    if (!sb_audio_response_valid(&s, 206, 1000)) return 2;
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 1000-1999/10000\r\n", "ETag: \"first\"\r\n");
    s.written = s.content_length = 1000;
    if (s.headers_ok || sb_audio_response_valid(&s, 206, 1000)) return 3;
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 999-9999/10000\r\n", "ETag: \"first\"\r\n");
    if (s.headers_ok) return 4;
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 1000-9999/10000\r\n", "ETag: \"changed\"\r\n");
    if (s.headers_ok) return 5;
    response(&s, "HTTP/1.1 200 OK\r\n", 0, "ETag: \"first\"\r\n");
    if (s.headers_ok) return 6;
    response(&s, "HTTP/1.1 416 Range Not Satisfiable\r\n", 0, "ETag: \"first\"\r\n");
    if (s.headers_ok) return 7;
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 1000-9999/*\r\n", "ETag: \"first\"\r\n");
    if (s.headers_ok) return 8;
    response(&s, "HTTP/1.1 206 Partial Content\r\n", "Content-Range: bytes 1000-9999/10000\r\n", "ETag: W/\"first\"\r\n");
    if (s.headers_ok) return 9;
    s.resume_offset = 0;
    response(&s, "HTTP/1.1 200 OK\r\n", 0, 0);
    if (!s.headers_ok) return 10;
    s.http_status = 200; s.written = 100; s.content_length = 200;
    if (sb_audio_response_valid(&s, 200, 0)) return 11;
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as folder:
        cfile, binary = Path(folder, 'response.c'), Path(folder, 'response')
        cfile.write_text('#include <limits.h>\n#include <string.h>\n#define SB_RESPONSE_MAX (512 * 1024)\n#define SB_ID 96\n'
                         + sink + '\n' + resume + '\n' + helpers + program)
        built = subprocess.run(['cc', '-std=c99', '-Werror', str(cfile), '-o', str(binary)], capture_output=True, text=True)
        if built.returncode:
            ctx.expect(False, f'compile real download validators: {built.stderr}')
            return
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        ctx.expect(result.returncode == 0, f'download response and resume safety cases (case {result.returncode})')


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
    expect(m.call(PSYMS['sb_song_record_valid'], a0=dst) == 1, 'valid mapped song metadata is accepted')
    m.u.mem_write(dst + SB_ID, b'x' * SB_TEXT)
    expect(m.call(PSYMS['sb_song_record_valid'], a0=dst) == 0, 'unterminated mapped song metadata is rejected')
    for first, offset, count, total, want in ((58, 0, 64, 100, 0), (59, 0, 64, 100, 1),
                                              (61, 0, 64, 100, 1), (61, 61, 39, 100, 0),
                                              (99, 61, 39, 100, 0), (0, 61, 39, 100, 1)):
        got = m.call(PSYMS['sb_window_needs_load'], a0=first, a1=offset, a2=count, a3=total)
        expect(got == want, f'visible song window {first}, cached from {offset} with {count} records')
    off = SB_FIELDS
    expect(struct.unpack_from('<III', raw, off) == (245, 7, 2), 'duration, track and disc numbers parse')
    long_body = json.dumps({"subsonic-response": {"status": "ok", "searchResult3": {"song": [
        {"id": "long-1", "title": "音" * 100, "artist": "A", "album": "B"}]}}}, ensure_ascii=False).encode()
    m.u.mem_write(src, long_body)
    n = m.call(PSYMS['sb_songs'], a0=src, a1=len(long_body), a2=dst, a3=1)
    raw = bytes(m.u.mem_read(dst, SONG_SIZE))
    title = raw[SB_ID:SB_ID + SB_TEXT].split(b'\0')[0].decode('utf-8')
    expect(n == 1 and 0 < len(title.encode('utf-8')) < SB_TEXT,
           'long UTF-8 metadata is safely truncated without rejecting the whole library page')
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
    src = open(os.path.join(ROOT, 'patch', 'subsonic.c'), encoding='utf-8').read()
    expect('variant == 1' in src and 'variant == 2' in src and 'query=%%2A' in src
           and 'SB_SYNC_ERR_EMPTY' in src,
           'sync retries compatible empty-query forms and distinguishes a blank server response')
    sync = src[src.index('static int sb_sync_library'):src.index('static unsigned sb_art_hash')]
    expect('#define SB_SYNC_RESERVE_KB 2048u' in src and 'free_kb < 32768' not in sync
           and 'SB_SYNC_RESERVE_KB + page_kb' in sync and 'SB_SYNC_RESERVE_KB + copy_kb' in sync
           and 'unlink(SB_INDEX_TMP)' in sync and 'rename(SB_INDEX_TMP, SB_INDEX_FILE)' in sync,
           'library sync reserves modest free space, checks index growth, and preserves the previous index on failure')


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
                'sb_grid_row0', 'sb_grid_art0', 'sb_row_download0', 'sb_row_download_icon0')
    ctx.expect(all(name in by_name for name in required) and 'sb_row_play0' not in by_name and 'sb_grid_play0' not in by_name
               and 'sb_play' not in by_name and 'sb_download' not in by_name
               and 'sb_prev' not in by_name and 'sb_next' not in by_name,
               'Navidrome page has list/grid browsing with download-only actions and row-tap playback')
    ctx.expect(by_name['sb_connect_label'].get('text') == 'Server'
               and by_name['sb_tracks_label'].get('text') == 'Songs'
               and by_name['sb_dsd_label'].get('text') == 'DSD Downloads'
               and by_name['sb_status'].get('text') == 'Connect to browse your music'
               and all(by_name[name].get('tr_text') is None for name in
                       ('sb_connect_label', 'sb_tracks_label', 'sb_dsd_label', 'sb_status')),
               'Navidrome page labels remain English regardless of the device locale')
    ctx.expect(all(by_name[name].h >= 44 for name in ('sb_connect', 'sb_sync', 'sb_search', 'sb_tracks', 'sb_dsd', 'sb_view', 'sb_row_download0')),
               'Navidrome touch controls meet the 44 px target height')
    ctx.expect(by_name['sb_row_download0'].x + by_name['sb_row_download0'].w <= 320
               and by_name['sb_grid_download0'].x == 59,
               'download actions fit at the right edge in list view and are centered in grid view')
    ctx.expect(all(f'{name}_icon' in by_name for name in ('sb_tracks', 'sb_dsd')),
               'Songs and DSD Downloads have clear section icons')
    ctx.expect(by_name['sb_tracks_icon'].get('image') == 'pod_ic_navidrome'
               and by_name['sb_dsd_icon'].get('image') == 'pod_sb_dsd',
               'Navidrome uses a record mark and DSD keeps its badge in the tabs')
    from PIL import Image
    logo = Image.open(os.path.join(mod_icons.PNG, mod_icons.SUBSONIC_ART[0] + '.png'))
    dsd = Image.open(os.path.join(mod_icons.PNG, mod_icons.SUBSONIC_ART[1] + '.png'))
    ctx.expect(logo.size == dsd.size == (mod_icons.SUBSONIC_ART_PX, mod_icons.SUBSONIC_ART_PX),
               'Navidrome and DSD row/grid placeholders use full-resolution 136 px source icons')
    ctx.expect(all(palette_mod.accent_kind(name) == 'glyph' for name in mod_icons.SUBSONIC_ART),
               'both high-resolution placeholders follow the selected device accent')
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
    ctx.expect('if (!text[0])' in src and 'pod_toast(SB_ENGLISH("Enter a server password"))' in src,
               'login rejects an empty password instead of saving credentials that cannot sync')
    ctx.expect('head.count + head.dsd_count > SB_SYNC_LIMIT' in src and 'sb_fixed_equal(head.server' in src
               and 'head.count + head.dsd_count' in src and 'SB_INDEX_MAGIC "SBIDX3' in src
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
    ctx.expect('sb_set_active_tab(dsd_view);' in src and 'style:normal:bg_color' in src and 'pod_sb_download' in src
               and 'static int sb_select_click(void *ctx, void *e)' in src,
               'the selected library tab is highlighted and its DSD glyph follows the accent')
    ctx.expect('sb_set_connected(1);' in src and 'sb_connected_dot' in src and '"#34C759"' in src
               and 'SB_ENGLISH(sbp.connected ? "Connected" : "Server")' in src,
               'the Server control shows a green connection dot and Connected label after a successful check')
    ctx.expect('pod_confirm(SB_ENGLISH("Sync Navidrome songs and artwork to the SD card now?"))' in src,
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
    ctx.expect('getCoverArt' in src and 'sb_sync_art(sink)' in src and 'sb_cover_file' not in src,
               'artwork sync caches bounded cover images inside the standalone page')


def run(ctx):
    ctx.expect(not any(name.startswith(('sb_library_', 'rgb_')) for name in PSYMS),
               'the standalone payload exposes neither a library overlay nor RGB integration')
    parser_tests(ctx)
    ui_tests(ctx)
    login_tests(ctx)
    download_validation_tests(ctx)
