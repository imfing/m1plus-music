#!/usr/bin/env python3
"""Shared page/entry definitions for the M1+ Music payload.

One source of truth, consumed by both:
  tools/pod_ui.py   builds the ui/*.bin assets (widget trees)
  tools/pod.py      emits the C row/page tables into stock.h for patch/m1plus.c

Keeping the rows here means the asset a page shows and the action the payload takes on a tap can
never drift apart: the row's widget name, its label and its handler all come from one record.

Entry point: the payload hooks the Home screen's icon click dispatcher and intercepts exactly one
Home icon, HOME_ENTRY: the "M1+ Music" icon patch/home.c adds to the stock grid (id 99, which stock never
uses). Tapping it opens the entry page (PAGES[0]); the kill-switch file and every other icon (Tidal
included) fall through to stock behaviour.
"""

# Home item ids (must match patch/offsets.inc HOME_*). The entry icon and the destinations rows open.
HOME_TIDAL = 1
HOME_UPDATE = 2      # systemset/updatemusic_page: Update Library
HOME_MYMUSIC = 3     # allmusic_page 0xf001: all songs
HOME_FOLDER = 4
HOME_GENRE = 7
HOME_COMPOSER = 8
HOME_HIRES = 9
HOME_FAV = 10
HOME_MOST = 11
HOME_RECENT = 12
HOME_RECENTADD = 13
HOME_PLAYLIST = 14
HOME_CDRIPPER = 15
HOME_PLAYSET = 16
HOME_SYSSET = 17

HOME_ENTRY = 99   # the id of the added "M1+ Music" grid icon (no stock id; the dispatcher's table ends at 17)

# Row actions (mirror the enum in patch/m1plus.c).
ACT_HOME = 0     # open a stock Home destination through the stock dispatcher (arg = HOME_* id)
ACT_PAGE = 1     # open another M1+ Music page (arg = page index in PAGES)
ACT_PLAYER = 2   # go to Now Playing (stock on_backtoplayer_onclick)
ACT_COVER = 3    # open Cover Flow (patch/coverflow.c; its own page, built at runtime)
ACT_SHUFFLE = 4  # shuffle the library and play it (patch/shuffle.c; arg = SHUFFLE_*)
ACT_ARTISTS = 8  # open the Artists list (patch/artists.c; rows built at runtime from the stock query); arg 0 Artists, HOME_GENRE / HOME_COMPOSER: Genres / Composers on the same page
ACT_ALBUMS = 11  # open Albums in the last-used view: the grid (patch/albums.c) or the stock list
ACT_GRID = 9     # show the stock Shanling grid for this session (patch/home.c)
ACT_STARTUP = 10 # switch row: the persistent "Boot to M1+ Music" setting (patch/home.c)
ACT_LANDSCAPE = 12  # switch row: Cover Flow opens in landscape (patch/coverflow.c)
ACT_SORT = 13    # value row: the album order of Cover Flow and Albums, Artist or Album; a tap toggles (patch/covercache.c)
ACT_SHOT = 14    # the Screenshot row (Settings): a 5 s countdown, then the screen is written to /mnt/mmc/screenshots (patch/shot.c)
ACT_REBUILD = 15 # the Rebuild Covers row (Settings > Cover Flow): a confirm dialog, then a request that Home's cover build acts on (patch/m1plus.c, patch/homecover.c)
ACT_SHELF = 16    # switch row: the Recently Played shelf on the Home menu (patch/recent.c)
ACT_PLAYLISTS = 17  # open the Playlists page: a grid of mosaics of each playlist's album covers (patch/playlists.c)
ACT_SONGS = 18      # open the Songs page: the library as one list with a large title, sections and a jump rail (patch/songs.c)
ACT_DAILY = 19   # switch row: the Daily Mix card on the Home menu (patch/dailymix.c)
ACT_REGEN = 20   # action row (no chevron, like the Shuffle rows): make today's Daily Mix again with a new seed (patch/dailymix.c)
ACT_LIST = 21    # open a stock song list on the Songs page (patch/songs.c songs_open_list; arg = its HOME_* tile, where a window that will not open falls back)
ACT_IPOD = 22    # open the Pod, the virtual iPod Classic page: a fullscreen window with a touch click wheel (patch/ipod.c ipod_open)
ACT_PODCASTS = 23   # open the Podcasts page: the shows in /mnt/mmc/Podcasts and their episodes (patch/podcasts.c podcasts_open)
ACT_RADIO = 50    # open the Radio page: Stations, Recently Played, Radio Browser (the directory's top stations, countries and genres, a station's search) (patch/radiopage.c radio_open)
ACT_SUBSONIC = 51 # Navidrome/Subsonic remote library and playback (patch/subsonic.c)
ACT_SEARCH = 35   # open the library search page (patch/search.c search_open; the stock search_page where ours will not open), the Search item of the menu and Extras
ACT_KB_EN = 27  # switch row (Settings > Keyboards): English, always on and not switchable (the row's switch is shown on and the row is dimmed)
ACT_KB_ZH = 28  # switch row (Settings > Keyboards): Chinese (Pinyin), off by default; on gives the on-screen keyboard a language key and the pinyin layer (patch/keyboard.c kb_zh_toggle)
ACT_CTHEME = 24  # value row: the Cassette Mode theme, Normal, Chrome or Metal; opens its picker page (arg = the page index); the payload shows the saved theme (patch/tape.c tape_theme)
ACT_STOCK = 29   # open a stock page by name (arg = index in STOCK_PAGES; patch/m1plus.c navigator_to, no context); some show a value of the stock state at the right
ACT_SORTSET = 30   # picker row (Album Order): choose the album order (arg 1 Artist, 0 Album); a check shows on the chosen row (patch/covercache.c cc_sort_set)
ACT_THEMESET = 31  # picker row (Cassette Theme): choose the theme (arg 0 Normal, 1 Chrome, 2 Metal); a check shows on the chosen row (patch/tape.c tape_theme_set)
ACT_INFO = 33     # an information row of the About page: a label and a grey value at the right, no chevron, not tappable (arg = INFO_*: where patch/m1plus.c reads the value; INFO_STATIC: the Row's own text)
ACT_PCSEARCH = 34  # switch row (Settings > Library > Podcasts): Podcast Search, off by default; on shows a Search button on the Podcasts page (patch/podcasts.c pcsearch_toggle, /mnt/data/m1plus/podcast-online-search)
ACT_FOLDERS = 37  # open the Folders page: the card's folders and audio files in our list (patch/folders.c; arg = HOME_FOLDER, where a window that will not open falls back to the stock folder_page)
ACT_CLEARCACHE = 42  # action row (Settings > Developer > Tools): a confirm dialog, then every cached cover but Cover Flow's position is deleted in steps (patch/homecover.c homecover_clear)
ACT_CLEARDUR = 44  # action row (Settings > Developer > Tools): a confirm dialog, then the track durations table is deleted (patch/durations.c dur_clear); Home measures the songs again
ACT_CCLIST = 43    # value row (Settings > Developer > Cover Cache: No art, Missing): a count, and when it is not zero a chevron and a tap that opens the plain list of those albums (arg = the INFO_CC_* of its count; patch/covlist.c)
ACT_BATTPCT = 36  # switch row (Settings > Home Screen > Status Bar): Battery Percentage, off by default; on shows the gauge's exact charge beside the battery outline (patch/battery.c battpct_toggle, /mnt/data/m1plus/battery-percentage)
ACT_VREC = 38     # value row (Settings > Now Playing > Vinyl Mode): the record colour, Black or Cover (tinted from the cover); opens its picker page (arg = the page index; patch/vinyl.c vinyl_record)
ACT_RECSET = 39   # picker row (Record): choose the colour (arg = its index in vinyl_art.RECORD_NAMES); a check shows on the chosen row (patch/vinyl.c vinyl_record_set)
ACT_VTHEME = 40   # value row (Settings > Now Playing > Vinyl Mode): the plinth theme, Graphite or White; opens its picker page (arg = the page index; patch/vinyl.c vinyl_theme)
ACT_VTHSET = 41   # picker row (Base): choose the theme (arg = its index in vinyl_art.THEME_NAMES); a check shows on the chosen row (patch/vinyl.c vinyl_theme_set)
ACT_UPDATE = 45   # link row (Settings > System > About): Software Update, our own page (patch/update.c update_open): check GitHub for a newer release, download it to the card, hand over to the stock TF card update
ACT_BG = 46       # value row (Settings > System > Appearance > Background): Black or Tinted; opens its picker page (arg = the page index); the payload shows the saved background (patch/palette.c pal_bg_mode)
ACT_BGSET = 47    # picker row (Background): choose the background (arg 0 Black, 1 Tinted); a check shows on the chosen row, and the choice applies at once (patch/palette.c pal_bg_set)
ACT_ACCENT = 48    # value row (Settings > System > Accent): the accent's name; opens its picker page (arg = the page index); the payload shows the saved accent (patch/palette.c pal_accent_saved)
ACT_ACCENTSET = 49 # picker row (Accent): choose the accent (arg = its index in ACCENT_VALUES); a check shows on the chosen row and the choice applies at once (patch/palette.c pal_accent_set)
_ACTS = [v for k, v in globals().items() if k.startswith('ACT_')]
assert len(set(_ACTS)) == len(_ACTS), 'two ACT_* share an id (patch/m1plus.c mirrors them)'
SWITCH_ACTIONS = (ACT_STARTUP, ACT_LANDSCAPE, ACT_SHELF, ACT_DAILY, ACT_KB_EN, ACT_KB_ZH, ACT_PCSEARCH, ACT_BATTPCT)
NO_CHEVRON_ACTIONS = (ACT_PLAYER, ACT_SHUFFLE, ACT_REGEN)   # rows that play or act in place (a switch or a value row has none either)
VALUE_ACTIONS = (ACT_SORT, ACT_CTHEME, ACT_VREC, ACT_VTHEME, ACT_CCLIST, ACT_BG, ACT_ACCENT)    # rows with a grey value at the right, left of the chevron (the widget pod_value<row>); they open a picker page (arg = its page index)
CHECK_ACTIONS = (ACT_SORTSET, ACT_THEMESET, ACT_RECSET, ACT_VTHSET, ACT_BGSET, ACT_ACCENTSET)   # picker rows: a check at the right of the chosen one (the image pod_check<row>), no icon
ACTION_ACTIONS = NO_CHEVRON_ACTIONS + (ACT_SHOT, ACT_REBUILD, ACT_CLEARCACHE, ACT_CLEARDUR, ACT_GRID)   # rows that act in place on a settings page: no chevron (Update Library, an ACT_HOME row, is one too: row_kind)
VALUE_INIT = {ACT_SORT: 'Artist', ACT_CTHEME: 'Normal', ACT_VREC: 'Black', ACT_VTHEME: 'Graphite', ACT_BG: 'Black', ACT_ACCENT: 'Neutral'}   # what the asset's value label says before the payload sets it
# The stock pages ACT_STOCK opens: (the name navigator_to takes = ui/<name>.bin, the value the row shows at the right: the payload reads the stock state, patch/m1plus.c VK_*, or None).
# Each is a plain navigator_to(name) with no context in stock (docs/modules/settings.md "Stock pages"): the Settings and Play Settings lists' rows, the Wi-Fi hub's two; Back returns to our page.
STOCK_WIFI, STOCK_BLUETOOTH, STOCK_PLAYMODE, STOCK_EQ, STOCK_DISPLAY, STOCK_FWUPDATE = range(6)
STOCK_PAGES = (('systemset/wifi_page', 'wifi'), ('systemset/bluetooth_page', 'bluetooth'), ('playset/playmode_page', 'playmode'), ('playset/equalizer_page', 'eq'),
               ('systemset/display_page', None), ('systemset/fwupdate_page', None))
STOCK_VALUES = ('wifi', 'bluetooth', 'playmode', 'eq')   # the VK_* of patch/m1plus.c, in this order

# ACT_SHUFFLE arguments (mirror the enum in patch/shuffle.c)
SHUFFLE_SONGS = 0    # every song, stock Shuffle play mode, from a random song
SHUFFLE_ALBUMS = 1   # albums in random order, each album's tracks in order
SHUFFLE_FOLDERS = 2  # folders in random order, each folder's files in order


class Row:
    def __init__(self, label, action, arg=0):
        self.label, self.action, self.arg = label, action, arg


def row_kind(row):
    """How a settings row is drawn: 'switch', 'value' (a grey value and the chevron), 'check', 'info' (a grey value, no chevron, no touch), 'action' (no accessory) or 'link' (the chevron)."""
    if row.action in SWITCH_ACTIONS: return 'switch'
    if row.action in VALUE_ACTIONS or (row.action == ACT_STOCK and STOCK_PAGES[row.arg][1]): return 'value'
    if row.action in CHECK_ACTIONS: return 'check'
    if row.action == ACT_INFO: return 'info'
    if row.action in ACTION_ACTIONS or (row.action == ACT_HOME and row.arg == HOME_UPDATE): return 'action'
    return 'link'


class Hdr:
    """A section header of a cards page (grey text above a card)."""
    def __init__(self, text): self.text = text


class Note:
    """A grey note under a card."""
    def __init__(self, text): self.text = text


GAP = 'gap'   # in a cards page's layout: the space between two cards that have no header or note between them


class Page:
    def __init__(self, key, name, title, rows=(), kind='rows', layout=None):
        self.key = key          # asset basename under ui/ (ui/<key>.bin) and window resource name
        self.name = name        # root widget name property
        self.title = title      # navbar title text
        self.layout = list(layout) if layout is not None else None   # a cards page: the Rows, Hdrs, Notes and GAPs in order (tools/pod_settings.py places them)
        if layout is not None: kind, rows = 'cards', [x for x in layout if isinstance(x, Row)]
        self.rows = list(rows)
        self.kind = kind        # 'rows', 'cards' (a Settings page: layout), 'cover' (Cover Flow's own layout), 'artists' (the A-Z list page the payload
                                # fills: Artists, Genres, Composers) or 'grid' (the Albums grid)


# The M1+ Music menu, the Classic iPod main menu adapted to the 320x480 touch screen (q2-pod
# docs/ipod.md geometry). Nineteen customisable items (the nine menu items, the nine Extras tiles and Settings), then Extras,
# which is always shown, always last and not customisable. The asset holds every row in the default order (an item's id is its row
# index); patch/menu.c hides the items the user hid (the Extras page lists them unless the user turned them off there) and orders the
# rest, as the saved list in /mnt/data/m1plus/home-menu says. Shuffle opens the Shuffle page, Artists the payload's
# Artists list, Settings the Settings page (cards: Wi-Fi, Bluetooth, the M1+ Music pages, Playback, System,
# Developer). Settings is hidden from the menu by default like Shuffle; it then shows on the Extras page (Tools), where it can never be turned off.
SHUFFLE_PAGE_INDEX = 3   # its index in PAGES
SETTINGS_PAGE_INDEX = 4
EXTRAS_PAGE_INDEX = 5
MENUCFG_PAGE_INDEX = 7
LIBRARY_PAGE_INDEX = 8
NPSET_PAGE_INDEX = 18
KEYBOARDS_PAGE_INDEX = 20
HOMESET_PAGE_INDEX = 9
EXTRASCFG_PAGE_INDEX = 13
DEVELOPER_PAGE_INDEX = 14
SORT_PAGE_INDEX = 21
THEME_PAGE_INDEX = 22
ABOUT_PAGE_INDEX = 23
RECORD_PAGE_INDEX = 29
VINYL_WHITE_INDEX = 30
VTHEME_PAGE_INDEX = 31
BG_PAGE_INDEX = 38   # after UPDATE
ACCENT_PAGE_INDEX = 39  # after BG_PAGE
APPEARANCE_PAGE_INDEX = 40  # after ACCENT_PAGE
PULLDOWN_PAGE_INDEX = 41   # before the Radio pages
ITEMS = [   # item id = index; the default order, essentials first (iPod classic style)
    Row('Now Playing', ACT_PLAYER),
    Row('Cover Flow', ACT_COVER),
    Row('Albums', ACT_ALBUMS),
    Row('Artists', ACT_ARTISTS),
    Row('Songs', ACT_SONGS),
    Row('Playlists', ACT_PLAYLISTS),
    Row('Shuffle', ACT_PAGE, SHUFFLE_PAGE_INDEX),
    Row('Genres', ACT_ARTISTS, HOME_GENRE),
    Row('Folders', ACT_FOLDERS, HOME_FOLDER),
    # The stock Home tiles the menu does not repeat (Songs, Albums, Artists, Genres, Folders and Playlists are items above,
    # Play/System Settings are on Settings; the HiFi Store, id 0, exists on the grid only in Simplified Chinese and is left
    # out). They are items too, hidden by default: Settings > Main Menu can show any of them in the menu. The five song lists (Favorites, Recently Added,
    # Recently Played, Most Played, Hi-Res) open on our Songs page (ACT_LIST, docs/modules/songs.md "The other lists"), the rest their stock page.
    Row('Favorites', ACT_LIST, HOME_FAV),
    Row('Recently Added', ACT_LIST, HOME_RECENTADD),
    Row('Recently Played', ACT_LIST, HOME_RECENT),
    Row('Most Played', ACT_LIST, HOME_MOST),
    Row('Composers', ACT_ARTISTS, HOME_COMPOSER),
    Row('Hi-Res', ACT_LIST, HOME_HIRES),
    Row('Update Library', ACT_HOME, HOME_UPDATE),
    Row('Tidal', ACT_HOME, HOME_TIDAL),
    Row('CD Ripper', ACT_HOME, HOME_CDRIPPER),
    # The Settings page (was the always-shown Settings row): an item like the others, hidden from the menu by default (a Tool on Extras).
    Row('Settings', ACT_PAGE, SETTINGS_PAGE_INDEX),
    # The Pod, the virtual iPod Classic (docs/modules/ipod.md): an item like the rest, hidden from the menu by default (on Extras, in Play).
    Row('Pod', ACT_IPOD),
    # Podcasts (docs/modules/podcasts.md): the shows on the card and their episodes; an item like the rest, hidden from the menu by default (on Extras, in Play).
    Row('Podcasts', ACT_PODCASTS),
    # Search (docs/modules/search.md): the library search page; an item like the rest, hidden from the menu by default (on Extras, in Library).
    Row('Search', ACT_SEARCH),
    # Radio (docs/modules/radio.md): internet radio stations; an item like the rest, hidden from the menu by default (on Extras, in Library, after Podcasts).
    Row('Radio', ACT_RADIO),
    Row('Navidrome', ACT_SUBSONIC),
]
SETTINGS_ID = 18
assert ITEMS[SETTINGS_ID].label == 'Settings'
# The saved menu (/mnt/data/m1plus/home-menu, patch/menu.c) stores these ids, so they are frozen: a new item is
# appended here and to ITEMS; never insert, remove or reorder (that silently remaps a saved menu). Display order
# comes from DEFAULT_MENU and EXTRAS_GROUPS, not from the id.
ITEM_IDS = ('Now Playing', 'Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Shuffle', 'Genres', 'Folders',
            'Favorites', 'Recently Added', 'Recently Played', 'Most Played', 'Composers', 'Hi-Res', 'Update Library',
            'Tidal', 'CD Ripper', 'Settings', 'Pod', 'Podcasts', 'Search', 'Radio', 'Navidrome')
assert tuple(r.label for r in ITEMS[:len(ITEM_IDS)]) == ITEM_IDS, 'menu item ids are frozen: append new items, never insert or reorder'
DEFAULT_MENU = [1, 2, 3, 4, 5]   # the items shown by default, in order (saved string "12345"): Cover Flow, Albums, Artists, Songs, Playlists, then Extras. A minimal menu: Now Playing is not
                                    # among them (the mini player bar of the Home instance opens it, docs/modules/minibar.md), nor are Shuffle and Settings; every other item is on the Extras page,
                                    # grouped (EXTRAS_GROUPS), and Settings > Main Menu can show any of them
assert all(0 <= i < len(ITEMS) for i in DEFAULT_MENU) and len(set(DEFAULT_MENU)) == len(DEFAULT_MENU)
ID_CHARS = '012345678abcdefghijklmno'   # one saved-list character per menu item
assert len(ID_CHARS) == len(ITEMS)
OFF_CHAR = '-'           # the saved list's separator: the item characters after it are turned off (not listed on the Extras page); at most once
DEFAULT_OFF = []         # no item is turned off by default
MENU_FILE_MAX = 27       # 24 item characters, optional off separator, newline and NUL
MENU = Page('m1plus_menu', 'm1plus_menu_page', 'M1+ Music', rows=ITEMS + [
    Row('Extras', ACT_PAGE, EXTRAS_PAGE_INDEX),   # always shown, always last
])


def parse_menu_full(data):
    """(the visible items in menu order, the items turned off) from the saved list (patch/menu.c mn_load's model), or the
    defaults. A line of item characters (ID_CHARS), then optionally OFF_CHAR and more item characters (the items the
    Extras page leaves out), then an optional newline, shorter than the file cap. Invalid, giving the default
    ([DEFAULT_MENU], []): an unknown character, an id twice (in either part or across them), a second OFF_CHAR, or
    Settings (SETTINGS_ID) after it (it can never be turned off: it must stay reachable)."""
    if isinstance(data, str): data = data.encode('latin-1')
    default = (list(DEFAULT_MENU), list(DEFAULT_OFF))
    if data is None or not 0 < len(data) < MENU_FILE_MAX: return default
    body = (data[:-1] if data.endswith(b'\n') else data).decode('latin-1')
    shown, sep, off = body.partition(OFF_CHAR)
    if OFF_CHAR in off or any(c not in ID_CHARS for c in shown + off): return default
    ids, offs = [ID_CHARS.index(c) for c in shown], [ID_CHARS.index(c) for c in off]
    if len(set(ids + offs)) != len(ids) + len(offs) or SETTINGS_ID in offs: return default
    return ids, offs


def parse_menu(data):
    """The visible items in menu order of the saved list (parse_menu_full without the turned-off items)."""
    return parse_menu_full(data)[0]


def format_menu(ids, off=()):
    """The saved list for the shown items and the turned-off ones, newline included (patch/menu.c mn_save). No OFF_CHAR
    when nothing is off; the off items in the Extras order (EXTRAS_ORDER)."""
    off = [i for i in EXTRAS_ORDER if i in off]
    return ''.join(ID_CHARS[i] for i in ids) + (OFF_CHAR + ''.join(ID_CHARS[i] for i in off) if off else '') + '\n'


# Cover Flow's own page (patch/coverflow.c fills it at runtime: the slide_menu of covers, the
# progress/cancel pair of the first-run cache build, and the album's track list).
COVER = Page('m1plus_cover', 'm1plus_cover_page', 'Cover Flow', kind='cover')
# Artists: the stock Artists query as an A-Z list in the Songs page's manner; a tap opens Cover Flow on that artist's albums.
ARTISTS = Page('m1plus_artists', 'm1plus_artists_page', 'Artists', kind='artists')
# Albums: the grid of covers or the list (patch/albums.c draws both in one custom view); the navbar button switches the mode.
ALBUMS = Page('m1plus_albums', 'm1plus_albums_page', 'Albums', kind='grid')
# Playlists: the stock playlists as a grid, each a mosaic of its albums' covers (patch/playlists.c); the "..." button opens the popup menu.
PLAYLISTS = Page('m1plus_playlists', 'm1plus_playlists_page', 'Playlists', kind='playlists')
# The popup menu's rows (tools/pod_ui.py builds them as the buttons pl_item0 ..; patch/playlists.c binds them by that order): New, Import, Export
# are the stock keys of the stock Playlists page's rows; Delete opens that page, whose multi-select button deletes.
PLAYLIST_MENU = ('New playlist', 'Import playlist', 'Export playlist', 'Delete Playlists')
# Songs: the library as one list (patch/songs.c): a large title, Play / Shuffle pills, sections with a pinned header and the A-Z rail (Title order), the navbar's
# Search / Sort / Select buttons. The sort card's rows are the stock sort dialog's labels (tools/pod_ui.py builds them as sg_item0 ..; the order is the stock
# sort_flag 0..4, patch/songs.c writes the flag the way the stock dialog's row handler does).
SONGS = Page('m1plus_songs', 'm1plus_songs_page', 'Songs', kind='songs')
SORT_MENU = ('sort_alphabet', 'sort_filename', 'sort_format', 'sort_time_desc', 'sort_time_asc')   # the stock keys of sort_flag 0..4
SHUFFLE_PAGE = Page('m1plus_shuffle', 'm1plus_shuffle_page', 'Shuffle', rows=[
    Row('Shuffle Songs', ACT_SHUFFLE, SHUFFLE_SONGS),
    Row('Shuffle Albums', ACT_SHUFFLE, SHUFFLE_ALBUMS),
    Row('Shuffle Folders', ACT_SHUFFLE, SHUFFLE_FOLDERS),
])

# Settings (iOS style grouped cards, tools/pod_settings.py places them; the design is tools/preview_settings.py's): the stock Wi-Fi and Bluetooth pages, the M1+ Music pages
# (Home Screen, Library, Now Playing, Keyboards), Playback (Play Mode, EQ, the stock Play Settings list) and System (Display, Appearance, Keyboards, About, the stock
# System Settings list), then Developer. Every "stock page" row is a plain navigator_to of the page stock's own list calls (STOCK_PAGES).
SETTINGS_PAGE = Page('m1plus_settings', 'm1plus_settings_page', 'Settings', layout=[
    Row('Wi-Fi', ACT_STOCK, STOCK_WIFI),
    Row('Bluetooth', ACT_STOCK, STOCK_BLUETOOTH),
    GAP,
    Row('Home Screen', ACT_PAGE, HOMESET_PAGE_INDEX),
    Row('Library', ACT_PAGE, LIBRARY_PAGE_INDEX),
    Row('Now Playing', ACT_PAGE, NPSET_PAGE_INDEX),
    Hdr('Playback'),
    Row('Play Mode', ACT_STOCK, STOCK_PLAYMODE),
    Row('EQ', ACT_STOCK, STOCK_EQ),
    Row('All Playback Settings', ACT_HOME, HOME_PLAYSET),
    Hdr('System'),
    Row('Display', ACT_STOCK, STOCK_DISPLAY),
    Row('Appearance', ACT_PAGE, APPEARANCE_PAGE_INDEX),
    Row('Keyboards', ACT_PAGE, KEYBOARDS_PAGE_INDEX),
    Row('About', ACT_PAGE, ABOUT_PAGE_INDEX),
    Row('All System Settings', ACT_HOME, HOME_SYSSET),
    GAP,
    Row('Developer', ACT_PAGE, DEVELOPER_PAGE_INDEX),
])

# Settings > System > About (our own page: the stock About page's seven values in sections, read the way stock reads them; docs/modules/settings.md "About"). INFO_* say where patch/m1plus.c reads
# a row's value: the build tag, the stock firmware version literal, the model literal, the serial number, the Wi-Fi MAC, the IP address (while connected), the card's capacity and free space.
INFO_TAG, INFO_FW, INFO_MODEL, INFO_SN, INFO_MAC, INFO_IP, INFO_CAP, INFO_FREE = range(8)
ABOUT_PAGE = Page('m1plus_about', 'm1plus_about_page', 'About', layout=[
    Row('M1+ Music', ACT_INFO, INFO_TAG),
    Row('Software Update', ACT_UPDATE),
    Row('Firmware', ACT_INFO, INFO_FW),
    Hdr('Device'),
    Row('Model', ACT_INFO, INFO_MODEL),
    Row('Serial Number', ACT_INFO, INFO_SN),
    Row('Wi-Fi MAC', ACT_INFO, INFO_MAC),
    Row('IP Address', ACT_INFO, INFO_IP),
    Hdr('Storage'),
    Row('Capacity', ACT_INFO, INFO_CAP),
    Row('Available', ACT_INFO, INFO_FREE),
])

# Settings > Developer > Cover Cache (patch/homecover.c, docs/modules/settings.md "Cover Cache"): the cache folder's counts (INFO_CC_*: homecover_stat reads each, an ellipsis until counted), the build's Status
# and the Clear Cover Cache action.
INFO_CC_ALBUMS, INFO_CC_COVERS, INFO_CC_NOART, INFO_CC_MISSING, INFO_CC_OLD, INFO_CC_SIZE, INFO_CC_STATUS = range(8, 15)   # (patch/m1plus.c INFO_CC = 8 + the index homecover_stat takes)
CACHE_PAGE_INDEX = 33   # after ONLINEART (32)
CACHE_PAGE = Page('m1plus_cache', 'm1plus_cache_page', 'Cover Cache', layout=[
    Row('Albums', ACT_INFO, INFO_CC_ALBUMS),
    Row('Covers', ACT_INFO, INFO_CC_COVERS),
    Row('No art', ACT_CCLIST, INFO_CC_NOART),
    Row('Missing', ACT_CCLIST, INFO_CC_MISSING),
    Row('Old files', ACT_INFO, INFO_CC_OLD),
    Row('Size', ACT_INFO, INFO_CC_SIZE),
    GAP,
    Row('Status', ACT_INFO, INFO_CC_STATUS),
    GAP,
    Row('Clear Cover Cache', ACT_CLEARCACHE),
])

# The plain list behind the Cover Cache page's No art / Missing rows (patch/covlist.c, docs/modules/settings.md "Cover Cache"): the Albums page's asset without its toggle and Cover Flow button, the title set by the payload.
COVLIST = Page('m1plus_covlist', 'm1plus_covlist_page', 'Missing Covers', kind='covlist')

# Settings > Developer > Tools > Settings Files (patch/setfiles.c, docs/modules/settings.md "Settings Files"): the payload's own files as read when the page opens. The labels are the file names (identifiers, not translated).
SETTING_FILES = ('albums-view', 'playlists-view', 'recently-added-view', 'album-order', 'coverflow-landscape', 'cassette-theme', 'vinyl-record', 'vinyl-base', 'pod-appearance', 'home-recent-albums',
                 'home-daily-mix', 'home-menu', 'pulldown-tiles', 'keyboard-pinyin', 'podcast-online-search', 'battery-percentage', 'playback-shuffle', 'search-history', 'radio-recent', 'covers-rebuild')
GUARD_FILES = ('m1plus-start', 'm1plus-run', 'm1plus-bad', 'm1plus-off')
FOLDER_LABEL = 'm1plus/'
INFO_SF = INFO_CC_STATUS + 1   # patch/m1plus.c INFO_SF = INFO_CC + 7; row k reads setfiles_stat(k): 4 guard files, the folder, the settings
FILES_PAGE_INDEX = 35   # after COVLIST (34)
FILES_PAGE = Page('m1plus_files', 'm1plus_files_page', 'Settings Files', layout=(
    [Row(f, ACT_INFO, INFO_SF + k) for k, f in enumerate(GUARD_FILES)] + [GAP, Row(FOLDER_LABEL, ACT_INFO, INFO_SF + 4)]
    + [Row(f, ACT_INFO, INFO_SF + 5 + k) for k, f in enumerate(SETTING_FILES)]))

# Settings > Developer: Startup (the Boot to M1+ Music switch, patch/home.c, and the way out to the stock grid) and the developer's tools. Screenshot: a confirm dialog, then a 5 s
# countdown (cancellable), then the screen is written to the card (patch/shot.c). System Update opens the stock firmware update page.
DEVELOPER_PAGE = Page('m1plus_developer', 'm1plus_developer_page', 'Developer', layout=[
    Hdr('Startup'),
    Row('Boot to M1+ Music', ACT_STARTUP),
    Row('Open Shanling Home', ACT_GRID),
    Note('Off: the device starts on Shanling Home'),
    Hdr('Tools'),
    Row('Screenshot', ACT_SHOT),
    Row('Cover Cache', ACT_PAGE, CACHE_PAGE_INDEX),
    Row('Clear Track Durations', ACT_CLEARDUR),
    Row('Settings Files', ACT_PAGE, FILES_PAGE_INDEX),
    Row('System Update', ACT_STOCK, STOCK_FWUPDATE),
])

# Settings > Home Screen: the Recent Albums and Daily Mix switches (the shelf and the card of the Home menu), . Then the two pages that arrange the menu (patch/menu.c), under a
# Status Bar header the Battery Percentage switch (patch/battery.c), and last Regenerate Daily Mix in a card of its own, which (with its note, pod_note4)
# is hidden while Daily Mix is off (patch/m1plus.c regen_show: the row and the note).
HOMESET_PAGE = Page('m1plus_homeset', 'm1plus_homeset_page', 'Home Screen', layout=[
    Row('Recent Albums', ACT_SHELF),
    Row('Daily Mix', ACT_DAILY),
    Note('Shown on Home below the menu'),
    Row('Main Menu', ACT_PAGE, MENUCFG_PAGE_INDEX),
    Note('Show, hide and reorder the menu'),
    Row('Extras', ACT_PAGE, EXTRASCFG_PAGE_INDEX),
    Note('Items the menu does not show'),
    Hdr('Status Bar'),
    Row('Battery Percentage', ACT_BATTPCT),
    Note('The exact charge beside the battery icon'),
    Row('Regenerate Daily Mix', ACT_REGEN),
    Note('A new mix the next time Home opens'),
])

# Main Menu: the customise page (patch/menu.c builds its behaviour at run time): one row per item with a
# show / hide switch (the row's own tap too) and, on the shown ones, an up arrow that moves it one place up.
MENUCFG_PAGE = Page('m1plus_mainmenu', 'm1plus_mainmenu_page', 'Main Menu', kind='menucfg')

# Pull-down (patch/pulldown.c, docs/modules/pulldown.md): the eight tiles of the stock pull-down (ui/dialog/dropdown_dialog.bin, view_switchs) in the stock slot order, which is the
# id of a tile ('0'..'7'). The page is the Main Menu page's twin (a row per tile with a switch and, on the shown rows but the first, an up arrow). The row labels are short texts of
# ours, not the tiles' stock captions: those ("Playback Setting", "Output Options"; far longer in Russian or Italian) do not fit the row's label beside the arrow.
PULLDOWN_TILES = ('Wi-Fi', 'Bluetooth', 'Button Lock', 'Gain', 'USB Mode', 'Output', 'Playback', 'System')
PULLDOWN_CHARS = '01234567'
PULLDOWN_FILE_MAX = 12   # patch/pulldown.c reads at most this many bytes (8 ids, the '-' and a newline are 10); longer is invalid
PULLDOWN_PAGE = Page('m1plus_pulldown', 'm1plus_pulldown_page', 'Control Center', kind='pdcfg')


def parse_pulldown(data):
    """The shown tile ids in order from the saved file (patch/pulldown.c pd_load's model), or the default (all eight, stock order).
    `<shown ids>[-<hidden ids>]` and an optional newline, 1 .. PULLDOWN_FILE_MAX - 1 bytes; every other tile is hidden (the part after
    the '-' only says in what order the editor lists them). Invalid, giving the default: an unknown character, an id twice (in either
    part or across them), a second '-'. A bare newline or '-' hides all eight."""
    if isinstance(data, str): data = data.encode('latin-1')
    default = list(range(len(PULLDOWN_TILES)))
    if data is None or not 0 < len(data) < PULLDOWN_FILE_MAX: return default
    body = (data[:-1] if data.endswith(b'\n') else data).decode('latin-1')
    shown, sep, hidden = body.partition('-')
    if '-' in hidden or any(c not in PULLDOWN_CHARS for c in shown + hidden): return default
    ids = [PULLDOWN_CHARS.index(c) for c in shown + hidden]
    if len(set(ids)) != len(ids): return default
    return ids[:len(shown)]


def format_pulldown(shown):
    """The saved file for the shown tiles (patch/pulldown.c pd_save): the ids, then '-' and the hidden ones in stock order, if any, and a newline."""
    hidden = [i for i in range(len(PULLDOWN_TILES)) if i not in shown]
    return ''.join(PULLDOWN_CHARS[i] for i in shown) + ('-' + ''.join(PULLDOWN_CHARS[i] for i in hidden) if hidden else '') + '\n'

# Extras (iPod style): every item the menu does not show and the user did not turn off (the asset has a row for each item, in id
# order, same index as the menu's; patch/menu.c hides the ones the menu shows or that are off and stacks the rest in EXTRAS_ORDER,
# the same for every language). The items are in four titled groups, in a deliberate order (not alphabetical; the title is the
# group's section header, a non-interactive caption, shown while the group has a row on the page): what plays, the library's
# views, the song collections, the tools. Settings is in none: it is the Extras page's navbar button.
EXTRAS_GROUPS = (
    ('Play', ('Now Playing', 'Shuffle', 'Pod')),
    ('Library', ('Albums', 'Artists', 'Songs', 'Playlists', 'Cover Flow', 'Genres', 'Composers', 'Folders', 'Podcasts', 'Radio', 'Search', 'Navidrome')),
    ('Collections', ('Favorites', 'Recently Played', 'Recently Added', 'Most Played', 'Hi-Res')),
    ('Tools', ('Update Library', 'CD Ripper', 'Tidal')),
)
_LABELS = [r.label for r in ITEMS]
# Settings is in no group and is never listed: the Extras page's navbar has a Settings button instead (the asset keeps its row for the
# index, hidden by the payload), and Settings > Extras has no row for it. Its id ends EXTRAS_ORDER, and its group is the sentinel len(EXTRAS_GROUPS).
EXTRAS_ORDER = [_LABELS.index(label) for _, group in EXTRAS_GROUPS for label in group] + [SETTINGS_ID]   # item ids, the flattened groups, then Settings
EXTRAS_GROUP_OF = [next((g for g, (_, labels) in enumerate(EXTRAS_GROUPS) if label in labels), len(EXTRAS_GROUPS)) for label in _LABELS]   # item id -> its group (Settings: none)
EXTRAS_TITLES = [title for title, _ in EXTRAS_GROUPS]
assert sorted(EXTRAS_ORDER) == list(range(len(ITEMS))) and len(set(EXTRAS_TITLES)) == len(EXTRAS_GROUPS)
HDR_H = 40         # the section header's strip: shorter than a row (patch/menu.c puts it above the group's first row)


def extras_display(ids, off=(), cfg=False):
    """The Extras page's children as patch/menu.c stacks them for the saved list (shown item ids `ids`, turned-off ids `off`):
    [('hdr', group)] and [('row', item id)] in display order, then the hidden ones last (the hidden headers in group order, then the hidden rows in
    EXTRAS_ORDER). A row is shown when the menu does not show the item and (Extras) the list did not turn it off, or (cfg: Settings > Extras, which
    has no row for Settings) whatever the list says about it off; Settings is never listed (on Extras its row is hidden: the navbar has its button); a header is shown only while its group has a shown row, right above it.
    Returns (shown, hidden)."""
    listed = (lambda i: i != SETTINGS_ID and i not in ids) if cfg else (lambda i: i != SETTINGS_ID and i not in ids and i not in off)
    shown, hidden = [], []
    for g in range(len(EXTRAS_GROUPS)):
        rows = [i for i in EXTRAS_ORDER if EXTRAS_GROUP_OF[i] == g and listed(i)]
        if rows: shown += [('hdr', g)] + [('row', i) for i in rows]
        else: hidden.append(('hdr', g))
    hidden += [('row', i) for i in EXTRAS_ORDER if not listed(i) and not (cfg and i == SETTINGS_ID)]
    return shown, hidden


def extras_layout(shown, row_h):
    """([(kind, key, y)], the list's height): the y of each shown child of extras_display, a header HDR_H high and a row row_h high, from 0."""
    out, y = [], 0
    for kind, key in shown:
        out.append((kind, key, y))
        y += HDR_H if kind == 'hdr' else row_h
    return out, y


EXTRAS_PAGE = Page('m1plus_extras', 'm1plus_extras_page', 'Extras', rows=[Row(r.label, r.action, r.arg) for r in ITEMS])

# Settings > Extras: which of the items the menu does not show the Extras page lists (patch/menu.c builds its behaviour at run time).
# A switch row (the whole row toggles) per item but Settings, in id order like the Extras page's asset; the payload shows only the
# items the menu does not show, stacked in EXTRAS_ORDER. Off = left out of Extras (the saved list's part after OFF_CHAR); showing
# an item in the menu (Main Menu) turns it on again, so an item hidden from the menu later is back on Extras.
EXTRASCFG_PAGE = Page('m1plus_extrascfg', 'm1plus_extrascfg_page', 'Extras', kind='extrascfg')

# Settings > Library: one card of Update Library (the stock page, as the Update Library item), Rebuild Covers (the stock confirm dialog, then Home's cover build extracts every
# cover again) and Album Order (its value at the right opens a picker; the same order is used by the Albums page and Cover Flow), then Cover Flow's Landscape switch.
LIBRARY_PAGE = Page('m1plus_library', 'm1plus_library_page', 'Library', layout=[
    Row('Update Library', ACT_HOME, HOME_UPDATE),
    Row('Rebuild Covers', ACT_REBUILD),
    Row('Album Order', ACT_SORT, SORT_PAGE_INDEX),
    Note('Albums and Cover Flow'),
    Hdr('Cover Flow'),
    Row('Landscape', ACT_LANDSCAPE),
    Hdr('Podcasts'),
    Row('Podcast Search', ACT_PCSEARCH),
    Note('Search words are sent to Apple.'),
])
# Settings > Library > Album Order: the picker (a check on the chosen row).
SORT_PAGE = Page('m1plus_albumorder', 'm1plus_albumorder_page', 'Album Order', layout=[
    Row('Artist', ACT_SORTSET, 1),
    Row('Album', ACT_SORTSET, 0),
    Note('Albums and Cover Flow'),
])
SORT_VALUES = ('Artist', 'Album')    # the value shown for the setting's two states (the default, Artist, first)

# The album page (patch/albumpage.c, docs/modules/album-page.md): an album's tracks under the glass controls; opened by cc_open_album, never from a menu row.
ALBUM_PAGE = Page('m1plus_album', 'm1plus_album_page', 'Album', kind='album')

# The Daily Mix page (patch/dailymix.c dp_*): opened by a tap on the Home card; it has no navbar and no rows of its own (the payload paints the songs).
DAILYMIX = Page('m1plus_dailymix', 'm1plus_dailymix_page', 'Daily Mix', kind='dailymix')

# The Pod page (patch/ipod.c): a fullscreen window, no navbar and no rows; the payload paints the Pod screen and takes the wheel's touches.
IPOD = Page('m1plus_ipod', 'm1plus_ipod_page', 'Pod', kind='ipod')

# The Podcasts page (patch/podcasts.c): the Albums page's structure (a navbar over a stock list holding one view the payload paints); two levels, the shows and a show's episodes.
PODCASTS = Page('m1plus_podcasts', 'm1plus_podcasts_page', 'Podcasts', kind='podcasts')

# The Radio pages (patch/radiopage.c, patch/radionp.c, docs/modules/radio.md): the stations page (a navbar over a stock list holding one view the payload paints; levels, a bottom sheet) and Radio's Now Playing.
RADIO = Page('m1plus_radio', 'm1plus_radio_page', 'Radio', kind='radio')
RADIONP = Page('m1plus_radionp', 'm1plus_radionp_page', 'Radio', kind='radionp')
RADIOINFO = Page('m1plus_radioinfo', 'm1plus_radioinfo_page', 'Station Info', kind='radioinfo')   # patch/radioinfo.c: Radio Now Playing's Station Info
SUBSONIC_PAGE = Page('m1plus_subsonic', 'm1plus_subsonic_page', 'Navidrome', kind='subsonic')

# The Tape page (patch/tape.c): a fullscreen window drawn landscape; the payload paints the cassette and takes the touches (opened from Now Playing's More dialog, not from a menu row).
TAPE = Page('m1plus_tape', 'm1plus_tape_page', 'Cassette Mode', kind='tape')

# The Vinyl page (patch/vinyl.c): a fullscreen turntable Now Playing page (portrait); the payload paints the record and takes the touches, the text is the page's labels
# (opened from Now Playing's More dialog, not from a menu row).
VINYL = Page('m1plus_vinyl', 'm1plus_vinyl_page', 'Vinyl Mode', kind='vinyl')
VINYL.theme = 'graphite'
# The same page under the White plinth theme (tools/vinyl_art.py THEMES): the text labels' colours differ, so it has its own asset (patch/vinyl.c opens the saved one).
VINYL_WHITE = Page('m1plus_vinyl_white', 'm1plus_vinyl_white_page', 'Vinyl Mode', kind='vinyl')
VINYL_WHITE.theme = 'white'

# Find Cover & Lyrics (patch/onlineart.c): the stock navbar over a content view the payload paints the cover thumbnails on, with the status and lyrics labels and one pill (opened from Now Playing's
# More dialog, not from a menu row).
ONLINEART = Page('m1plus_onlineart', 'm1plus_onlineart_page', 'Cover & Lyrics', kind='onlineart')

# Software Update (patch/update.c, docs/modules/update.md): the stock navbar over one centred block the payload fills (a glyph, a title, an explanation, a progress bar and one pill); opened by the Settings > System row.
UPDATE = Page('m1plus_update', 'm1plus_update_page', 'Software Update', kind='update')

# Release Notes (patch/relnotes.c): the offered release's notes behind the Software Update page's second pill; the stock navbar over a scrolling text, opened from that page only.
RELNOTES = Page('m1plus_relnotes', 'm1plus_relnotes_page', 'Release Notes', kind='relnotes')

# Settings > Now Playing: the cassette's look. Theme shows its value (Normal, Chrome or Metal) at the right and opens a picker; the choice is saved and the Tape page reads it when it opens.
NPSET_PAGE = Page('m1plus_npset', 'm1plus_npset_page', 'Now Playing', layout=[
    Hdr('Cassette Mode'),
    Row('Theme', ACT_CTHEME, THEME_PAGE_INDEX),
    Hdr('Vinyl Mode'),
    Row('Record', ACT_VREC, RECORD_PAGE_INDEX),
    Row('Base', ACT_VTHEME, VTHEME_PAGE_INDEX),
])
# Settings > Now Playing > Theme: the picker (a check on the chosen row).
THEME_PAGE = Page('m1plus_tapetheme', 'm1plus_tapetheme_page', 'Cassette Theme', layout=[
    Row('Normal', ACT_THEMESET, 0),
    Row('Chrome', ACT_THEMESET, 1),
    Row('Metal', ACT_THEMESET, 2),
    Note('Applies the next time Cassette Mode opens.'),
])
# Settings > Now Playing > Record: the picker for Vinyl Mode's record colour (a check on the chosen row); the saved index is vinyl_art.RECORD_NAMES'.
RECORD_PAGE = Page('m1plus_vinylrec', 'm1plus_vinylrec_page', 'Record', layout=[
    Row('Black', ACT_RECSET, 0),
    Row('Cover', ACT_RECSET, 1),
    Note('Applies the next time Vinyl Mode opens.'),
])
# Settings > Now Playing > Base: the picker for Vinyl Mode's plinth theme (a check on the chosen row); the saved index is vinyl_art.THEME_NAMES'.
VTHEME_PAGE = Page('m1plus_vinyltheme', 'm1plus_vinyltheme_page', 'Base', layout=[
    Row('Graphite', ACT_VTHSET, 0),
    Row('Snow', ACT_VTHSET, 1),
    Note('Applies the next time Vinyl Mode opens.'),
])
VTHEME_VALUES = ('Graphite', 'Snow')   # the value the Base row shows, in the order of the saved index
RECORD_VALUES = ('Black', 'Cover')   # the value the Record row shows, in the order of the saved index (tools/vinyl_art.py RECORD_NAMES)
CTHEME_VALUES = ('Normal', 'Chrome', 'Metal')   # the value shown for the setting's three states, in the order of the saved index (tools/tape_art.py THEME_NAMES)

# Settings > System > Appearance > Background (docs/modules/accent.md): the picker, a check on the chosen row. The choice applies at once (patch/palette.c pal_bg_set: cached images dropped, the screen
# repainted). The saved file also knows 2 Light and 3 Light Auto (patch/palette.c); they are not offered.
BG_PAGE = Page('m1plus_background', 'm1plus_background_page', 'Background', layout=[
    Row('Black', ACT_BGSET, 0),
    Row('Tinted', ACT_BGSET, 1),
])
BG_VALUES = ('Black', 'Tinted')   # the value the Background row shows for the saved background 0, 1

# Settings > System > Accent (docs/modules/accent.md): the picker, one row per accent with its round swatch where a row's glyph goes (the image pod_sw<arg>, tools/mod_icons.py) and a check on the
# chosen one. The choice applies at once (patch/palette.c pal_accent_set). ACCENT_VALUES is tools/palette.py ACCENTS in the saved order, as the names the rows show.
ACCENT_VALUES = ('Neutral', 'Red', 'Orange', 'Green', 'Teal', 'Purple', 'Champagne')
ACCENT_PAGE = Page('m1plus_accent', 'm1plus_accent_page', 'Accent', layout=[Row(n, ACT_ACCENTSET, i) for i, n in enumerate(ACCENT_VALUES)])

# Settings > System > Appearance: one card with the Background value row (Black or Tinted) and the Accent value row (the accent's name), each opening its picker; then a card
# with the Control Center link row (the pull-down's tiles, PULLDOWN_PAGE).
APPEARANCE_PAGE = Page('m1plus_appearance', 'm1plus_appearance_page', 'Appearance', layout=[Row('Background', ACT_BG, BG_PAGE_INDEX), Row('Accent', ACT_ACCENT, ACCENT_PAGE_INDEX),
                                                                                         GAP, Row('Control Center', ACT_PAGE, PULLDOWN_PAGE_INDEX)])

# The keyboard page (patch/keyboard.c, docs/modules/keyboard.md): the navbar, a search field and our own QWERTY pad; opened by keyboard_open (the Developer row, later podcast search), no menu row.
KEYBOARD = Page('m1plus_keyboard', 'm1plus_keyboard_page', 'Keyboard', kind='keyboard')

# Settings > Keyboards (iOS style): the keyboards the on-screen keyboard offers. English is always on (its switch is shown on and cannot be turned off); Chinese (Pinyin) is off by default.
# With it on, the keyboard page has a language key and a pinyin layer with a candidate strip (docs/modules/keyboard.md). The choice is saved in /mnt/data/m1plus/keyboard-pinyin (patch/keyboard.c).
KEYBOARDS_PAGE = Page('m1plus_keyboards', 'm1plus_keyboards_page', 'Keyboards', layout=[
    Row('English', ACT_KB_EN),
    Row('Chinese (Pinyin)', ACT_KB_ZH),
])

# The Search results page (patch/search.c, docs/modules/search.md): the plain navbar (Back, the query as the title, an edit-search button, Now Playing) over a stock list holding one content view the payload paints
# (Artists, Albums and Songs sections); opened by search_open after our keyboard, from the Songs page's Search and the album page's search disc, no menu row.
SEARCH = Page('m1plus_search', 'm1plus_search_page', 'Search', kind='search')

# The Folders page (patch/folders.c, docs/modules/folders.md): the Songs page's structure (the glass navbar, a large title, Play / Shuffle pills, a stock list holding one view the payload paints) over the stock folder state; one window for every level.
FOLDERS = Page('m1plus_folders', 'm1plus_folders_page', 'Folders', kind='folders')

# The Queue page (patch/queuepage.c, docs/modules/queue.md): the play queue under the glass controls; opened by Now Playing's queue button, no menu row.
QUEUE_PAGE = Page('m1plus_queue', 'm1plus_queue_page', 'Queue', kind='queue')

# PAGES[0] is the entry page.
PAGES = [MENU, COVER, ARTISTS, SHUFFLE_PAGE, SETTINGS_PAGE, EXTRAS_PAGE, ALBUMS, MENUCFG_PAGE, LIBRARY_PAGE, HOMESET_PAGE, PLAYLISTS, SONGS, DAILYMIX,
         EXTRASCFG_PAGE, DEVELOPER_PAGE, IPOD, PODCASTS, TAPE, NPSET_PAGE, KEYBOARD, KEYBOARDS_PAGE, SORT_PAGE, THEME_PAGE, ABOUT_PAGE, SEARCH, ALBUM_PAGE, VINYL, FOLDERS, QUEUE_PAGE,
         RECORD_PAGE, VINYL_WHITE, VTHEME_PAGE, ONLINEART, CACHE_PAGE, COVLIST, FILES_PAGE, UPDATE, RELNOTES, BG_PAGE, ACCENT_PAGE, APPEARANCE_PAGE, PULLDOWN_PAGE, RADIO, RADIONP, RADIOINFO, SUBSONIC_PAGE]
SUBSONIC_PAGE_INDEX = PAGES.index(SUBSONIC_PAGE)
assert PAGES[KEYBOARDS_PAGE_INDEX] is KEYBOARDS_PAGE
assert PAGES[NPSET_PAGE_INDEX] is NPSET_PAGE
assert PAGES[SHUFFLE_PAGE_INDEX] is SHUFFLE_PAGE and PAGES[SETTINGS_PAGE_INDEX] is SETTINGS_PAGE
assert PAGES[EXTRASCFG_PAGE_INDEX] is EXTRASCFG_PAGE and PAGES[DEVELOPER_PAGE_INDEX] is DEVELOPER_PAGE
assert PAGES[EXTRAS_PAGE_INDEX] is EXTRAS_PAGE and PAGES[MENUCFG_PAGE_INDEX] is MENUCFG_PAGE
assert PAGES[LIBRARY_PAGE_INDEX] is LIBRARY_PAGE and PAGES[HOMESET_PAGE_INDEX] is HOMESET_PAGE
assert PAGES[ABOUT_PAGE_INDEX] is ABOUT_PAGE and PAGES[RECORD_PAGE_INDEX] is RECORD_PAGE and PAGES[BG_PAGE_INDEX] is BG_PAGE and PAGES[ACCENT_PAGE_INDEX] is ACCENT_PAGE and PAGES[APPEARANCE_PAGE_INDEX] is APPEARANCE_PAGE
assert PAGES[VINYL_WHITE_INDEX] is VINYL_WHITE and PAGES[VTHEME_PAGE_INDEX] is VTHEME_PAGE and PAGES[CACHE_PAGE_INDEX] is CACHE_PAGE and PAGES[FILES_PAGE_INDEX] is FILES_PAGE
assert PAGES[PULLDOWN_PAGE_INDEX] is PULLDOWN_PAGE
assert PAGES[SORT_PAGE_INDEX] is SORT_PAGE and PAGES[THEME_PAGE_INDEX] is THEME_PAGE
