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
import pcregion

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
ACT_SUBSONIC = 93 # the Navidrome root page (patch/ndroot.c)
ACT_SEARCH = 35   # open the library search page (patch/search.c search_open; the stock search_page where ours will not open), the Search item of the menu and Extras
ACT_KB_EN = 27  # switch row (Settings > Keyboards): English, always on and not switchable (the row's switch is shown on and the row is dimmed)
ACT_KB_ZH = 28  # switch row (Settings > Keyboards): Chinese (Pinyin), off by default; on gives the on-screen keyboard a language key and the pinyin layer (patch/keyboard.c kb_zh_toggle)
ACT_CTHEME = 24  # value row: the Cassette Mode theme, Normal, Chrome or Metal; opens its picker page (arg = the page index); the payload shows the saved theme (patch/tape.c tape_theme)
ACT_STOCK = 29   # open a stock page by name (arg = index in STOCK_PAGES; patch/m1plus.c navigator_to, no context); some show a value of the stock state at the right
ACT_THEMESET = 31  # picker row (Cassette Theme): choose the theme (arg 0 Normal, 1 Chrome, 2 Metal); a check shows on the chosen row (patch/tape.c tape_theme_set)
ACT_PEQ = 57      # value row (Settings > Playback > EQ): what the equalizer plays (Off, the 10-Band EQ's curve or the preset's name); opens the Equalizer page (arg = its page index; patch/peq_ui.c)
ACT_INFO = 33     # an information row of the About page: a label and a grey value at the right, no chevron, not tappable (arg = INFO_*: where patch/m1plus.c reads the value; INFO_STATIC: the Row's own text)
ACT_PCSEARCH = 34  # switch row (Settings > Library > Podcasts): Podcast Discover, on by default; off hides Discover and the search level (patch/podcasts.c pcsearch_toggle, /mnt/data/m1plus/podcast-online-search)
ACT_FOLDERS = 37  # open the Folders page: the card's folders and audio files in our list (patch/folders.c; arg = HOME_FOLDER, where a window that will not open falls back to the stock folder_page)
ACT_CLEARCACHE = 42  # action row (Settings > Developer > Tools): a confirm dialog, then every cached cover but Cover Flow's position is deleted in steps (patch/homecover.c homecover_clear)
ACT_CLEARDUR = 44  # action row (Settings > Developer > Cache): a confirm dialog, then the track durations table is deleted (patch/durations.c dur_clear); Home measures the songs again
ACT_CCLIST = 43    # value row (Settings > Developer > Cache: No art, Missing): a count, and when it is not zero a chevron and a tap that opens the plain list of those albums (arg = the INFO_CC_* of its count; patch/covlist.c)
ACT_BATTPCT = 36  # switch row (Settings > System > Battery): Battery Percentage, off by default; on shows the gauge's exact charge beside the battery outline (patch/battery.c battpct_toggle, /mnt/data/m1plus/battery-percentage)
ACT_VREC = 38     # value row (Settings > Now Playing > Vinyl Mode): the record colour, Black or Cover (tinted from the cover); opens its picker page (arg = the page index; patch/vinyl.c vinyl_record)
ACT_RECSET = 39   # picker row (Record): choose the colour (arg = its index in vinyl_art.RECORD_NAMES); a check shows on the chosen row (patch/vinyl.c vinyl_record_set)
ACT_VTHEME = 40   # value row (Settings > Now Playing > Vinyl Mode): the plinth theme, Graphite or White; opens its picker page (arg = the page index; patch/vinyl.c vinyl_theme)
ACT_VTHSET = 41   # picker row (Base): choose the theme (arg = its index in vinyl_art.THEME_NAMES); a check shows on the chosen row (patch/vinyl.c vinyl_theme_set)
ACT_UPDATE = 45   # link row (Settings > System > About): Software Update, our own page (patch/update.c update_open): check GitHub for a newer release, download it to the card, hand over to the stock TF card update
ACT_BG = 46       # value row (Settings > System > Appearance > Background): Black or Tinted; opens its picker page (arg = the page index); the payload shows the saved background (patch/palette.c pal_bg_mode)
ACT_BGSET = 47    # picker row (Background): choose the background (arg 0 Black, 1 Tinted); a check shows on the chosen row, and the choice applies at once (patch/palette.c pal_bg_set)
ACT_ACCENT = 48    # value row (Settings > System > Accent): the accent's name; opens its picker page (arg = the page index); the payload shows the saved accent (patch/palette.c pal_accent_saved)
ACT_PEQ_SWITCH = 58  # the Equalizer page's rows (PEQ_PAGE.layout, not exported to the payload: patch/peq_ui.c binds them itself): stock's Equalizer switch ...
ACT_PEQ_PICK = 59    # ... and a picker row (10-Band EQ, a preset), a check on the one that plays
ACT_PEQ_AUTOEQ = 60  # ... and the Presets page's Download from AutoEq row (patch/autoeq.c autoeq_open)
ACT_PEQ_PRESET = 61  # a preset's picker row on the Equalizer page: the check (no chevron); a tap selects it
ACT_PEQ_PREAMP = 62  # the preset page's preamp row (PEQP_PAGE: a grey value, no chevron, no touch) ...
ACT_PEQ_BAND = 63    # ... and its band rows (two lines: the frequency and gain, the type and Q; no touch)
ACT_PEQ_PRESETS = 64  # the Equalizer page's last card: the link row Presets (a grey count of the preset files, the chevron; opens the Presets page: patch/peq_ui.c, patch/peqlib.c)
ACT_PEQ_LIB = 65      # a preset file's row on the Presets page: two lines (the name, a grey line), a chevron, 60 px (opens its Preset page: patch/peqlib.c)
ACT_PEQ_TENBAND = 67  # the Equalizer page's bottom card, first row: the link row 10-Band EQ (a grey curve name, the chevron; opens the 10-Band editor: patch/peq_ui.c, patch/tenband.c)
ACT_PEQ_TCURVE = 68   # the editor's Curve row (TENBAND_PAGE): a grey curve name and the chevron; opens the Curve page ...
ACT_PEQ_TPREAMP = 69  # ... its Preamp row (a grey "Auto · -5.0 dB" or "-3 dB", the chevron; opens the Preamp page) ...
ACT_PEQ_TRESET = 70   # ... and its Reset row (white, plain: no glyph, no chevron)
ACT_PEQ_CPICK = 71    # the Curve page's rows (a check on the current curve) ...
ACT_PEQ_PAUTO = 72    # ... and the Preamp page's Auto row (the cut Auto makes now in grey, then a check) ...
ACT_PEQ_PVAL = 73     # ... and its 0 dB .. -12 dB rows (the payload writes their text)
ACT_PEQ_DELETE = 66   # the Preset page's Delete Preset row: red, no glyph, no chevron (confirms, then unlinks the file: patch/peqpage.c, patch/peq_ui.c peq_delete)
ACT_PEQ_RENAME = 75   # the Preset page's Rename Preset row (white, plain: no glyph, no chevron), above Delete Preset in one card
ACT_LOCKON = 79   # switch row (Settings > Lock Screen > Enable): stock's lock screen switch, the byte screensaver_mode saved as [SYSSET] SCREENSAVER (patch/lockscreen.c lk_enabled_toggle)
ACT_LOCKSET = 88  # picker row (Lock Screen): choose the layout (arg 0 Large Cover, 1 Mini Player); a check shows on the chosen row; it applies the next time the lock screen opens (patch/lockscreen.c lk_layout_set)
ACT_VOLKEYS = 89  # switch row (Settings > Library > Cover Flow): Volume Buttons, off by default; on, the volume keys step our Cover Flow shelf (patch/coverflow.c cf_volkey)
ACT_PEQ_TSAVE = 76    # the 10-Band editor's Save as Preset row (white, plain, its own card at the bottom): the name entry, then a new preset file of the curve (patch/tenband.c tb_on_save)
ACT_ACCENTSET = 49 # picker row (Accent): choose the accent (arg = its index in ACCENT_VALUES); a check shows on the chosen row and the choice applies at once (patch/palette.c pal_accent_set)
ACT_SFDEL = 51    # information row of Settings Files (Settings > Developer > Tools): a setting file's label and its value, like ACT_INFO, but tappable while the file is there: a confirm, then the file is deleted (arg = INFO_SF + k; patch/setfiles.c setfiles_delete)
ACT_SFOLD = 52    # value row of Settings Files: Unsupported Files, the count of retired files (arg = INFO_SFOLD); a chevron and a tap that opens their list (patch/covlist.c kind 2) only while the count is not zero
ACT_SFDELALL = 53 # action row of Settings Files: Delete Unsupported Files, a confirm, then every retired file is deleted (patch/m1plus.c unsupported_delete_ask)
ACT_AZRAIL = 77   # switch row (Settings > Library): Index Rail, on by default; on shows the A-Z rail and its bubble on the A-Z lists (patch/azlist.c azrail_toggle, /mnt/data/m1plus/appearance-index-rail)
ACT_AZHEAD = 78   # switch row (Settings > Library): Section Headers, on by default; off drops the section letters and the pinned header and closes the rows up (patch/azlist.c azhead_toggle, /mnt/data/m1plus/appearance-headers)
ACT_RESETALL = 54 # action row of Developer > Tools: Reset All Settings, a confirm, then every settings file is deleted (patch/m1plus.c reset_all_ask, patch/setfiles.c setfiles_reset_all)
ACT_REGION = 55    # value row (Settings > Library > Podcasts): the Podcast Region, the storefront the podcast search and Discover use, or Automatic; opens its picker page (arg = the page index; patch/pcregion.c pcregion_value)
ACT_AREBUILD = 92  # action row (Settings > Library): Rebuild Artist Photos, a confirm dialog, then the request file Home's artist photo pass acts on (patch/m1plus.c arebuild_ask, patch/homecover.c)
ACT_REGIONSET = 56 # picker row (Podcast Region): choose Automatic (arg 0) or a storefront (arg = its index in pcregion.CODES + 1); a check shows on the chosen row (patch/pcregion.c pcregion_set)
ACT_NDVALUE = 94  # value row of the Navidrome Server page (patch/ndserver.c, tools/pod_ndserver.py): a grey value and the chevron, no glyph; that page binds its own rows, so no table of patch/m1plus.c has it
ACT_NDACT = 95    # action row of the Navidrome Server page: Sync Now, Sign Out (no accessory, no glyph)
ACT_CHGLIM = 80     # value row (Settings > System > Battery): Charge Limit, the saved limit ("80%" .. "100%"); opens its picker page (arg = the page index; patch/charging.c chg_limit)
ACT_CHGLIMSET = 81  # picker row (Charge Limit): choose the limit (arg = 80, 85, 90, 95 or 100, no limit); a check shows on the chosen row (patch/charging.c chg_set)
ACT_IDLE = 82       # value row (Settings > Now Playing > Idle Display): where Now Playing goes after ten seconds, Off, Album Cover, Cassette or Vinyl (the payload shows stock's Cover mode byte and the saved destination); opens its picker page (arg = the page index; patch/bigcover.c idle_choice)
ACT_IDLESET = 83    # picker row (Idle Display): choose Off (arg 0), Album Cover (1), Cassette (2) or Vinyl (3); a check shows on the chosen row (patch/bigcover.c idle_set)
ACT_LOCKWP = 84     # link row (Settings > Lock Screen): Wallpaper, our own picker page (patch/lockscreen.c lkwp_open).
ACT_LOCKSTYLE = 85  # value row (Settings > Lock Screen): Player Style, the saved layout (Large Cover / Mini Player); opens its picker page (arg = the page index; patch/lockscreen.c lk_layout)
ACT_LOCKINFO = 87   # link row (Settings > Lock Screen): Custom Wallpaper, the instructions on a Release Notes page of our own (patch/relnotes.c lockinfo_open)
ACT_NEXTALBUM = 90  # value row (Settings > Playback): Continue Playing, Off (the default) or Next Albums; opens its picker page (arg = the page index; patch/nextalbum.c na_setting). Next Albums plays the next album of the list an album was opened from when its queue ends (/mnt/data/m1plus/playback-next-album)
ACT_NASET = 91      # picker row (Continue Playing): choose the mode (arg = 0 Off, 1 Next Albums; 2 Auto Mix is planned); a check shows on the chosen row (patch/nextalbum.c na_set)
ACT_LOCKTIME = 86   # switch row (Settings > Lock Screen): Show Time, stock's lock screen clock switch, the byte screensaver_timeshow saved as [SYSSET] SSAVERTIMESHOW (patch/lockscreen.c lk_time_toggle)
_ACTS = [v for k, v in globals().items() if k.startswith('ACT_')]
assert len(set(_ACTS)) == len(_ACTS), 'two ACT_* share an id (patch/m1plus.c mirrors them)'
SWITCH_ACTIONS = (ACT_STARTUP, ACT_LANDSCAPE, ACT_SHELF, ACT_DAILY, ACT_KB_EN, ACT_KB_ZH, ACT_PCSEARCH, ACT_BATTPCT, ACT_PEQ_SWITCH, ACT_AZRAIL, ACT_AZHEAD, ACT_LOCKON, ACT_LOCKTIME, ACT_VOLKEYS)
NO_CHEVRON_ACTIONS = (ACT_PLAYER, ACT_SHUFFLE, ACT_REGEN)   # rows that play or act in place (a switch or a value row has none either)
VALUE_ACTIONS = (ACT_CTHEME, ACT_VREC, ACT_VTHEME, ACT_CCLIST, ACT_SFOLD, ACT_BG, ACT_ACCENT, ACT_REGION, ACT_PEQ, ACT_PEQ_PRESETS, ACT_PEQ_TENBAND, ACT_CHGLIM, ACT_LOCKSTYLE, ACT_IDLE, ACT_NEXTALBUM, ACT_NDVALUE)    # rows with a grey value at the right, left of the chevron (the widget pod_value<row>); they open a picker page (arg = its page index)
CHECK_ACTIONS = (ACT_THEMESET, ACT_RECSET, ACT_VTHSET, ACT_BGSET, ACT_ACCENTSET, ACT_LOCKSET, ACT_REGIONSET, ACT_CHGLIMSET, ACT_PEQ_PICK, ACT_PEQ_CPICK, ACT_PEQ_PAUTO, ACT_PEQ_PVAL, ACT_IDLESET, ACT_NASET)   # picker rows: a check at the right of the chosen one (the image pod_check<row>), no icon
ACTION_ACTIONS = NO_CHEVRON_ACTIONS + (ACT_SHOT, ACT_REBUILD, ACT_AREBUILD, ACT_CLEARCACHE, ACT_CLEARDUR, ACT_SFDELALL, ACT_RESETALL, ACT_GRID, ACT_NDACT)   # rows that act in place on a settings page: no chevron (Update Library, an ACT_HOME row, is one too: row_kind)
VALUE_INIT = {ACT_CTHEME: 'Normal', ACT_VREC: 'Black', ACT_VTHEME: 'Graphite', ACT_BG: 'Black', ACT_ACCENT: 'Neutral', ACT_REGION: 'Automatic', ACT_CHGLIM: '100%', ACT_LOCKSTYLE: 'Large Cover', ACT_IDLE: 'Album Cover', ACT_NEXTALBUM: 'Off', ACT_NDVALUE: ''}   # what the asset's value label says before the payload sets it
# The stock pages ACT_STOCK opens: (the name navigator_to takes = ui/<name>.bin, the value the row shows at the right: the payload reads the stock state, patch/m1plus.c VK_*, or None).
# Each is a plain navigator_to(name) with no context in stock (docs/modules/settings.md "Stock pages"): the Settings list's rows, the Wi-Fi hub's two; Back returns to our page.
# (The EQ row is ACT_PEQ: our Equalizer page, docs/modules/peq.md; stock's playset/equalizer_page is retired: its one caller opens the 10-Band editor, tools/pod.py EQ_ROW.)
STOCK_WIFI, STOCK_BLUETOOTH, STOCK_DISPLAY = range(3)
# (navigator path, value shown, window name): the window name is the asset's root widget name, which pod_open_stock restacks an opened window of instead of stacking a second one; None: always a new window.
# Only a page whose init does nothing that a restack would not redo has one (docs/modules/settings.md "Stock pages"): Display (nothing started). Wi-Fi: its init scans (wifi_scan) on every open and the foreground handler only rebuilds the list from the old results.
# Bluetooth: its background handler stops discovery (btStopSearch) and the foreground handler does not restart it, only init does.
STOCK_PAGES = (('systemset/wifi_page', 'wifi', None), ('systemset/bluetooth_page', 'bluetooth', None),
               ('systemset/display_page', None, 'display_page'))
STOCK_VALUES = ('wifi', 'bluetooth', 'eq')   # the VK_* of patch/m1plus.c, in this order ('eq': the EQ row's value, ACT_PEQ)

# ACT_SHUFFLE arguments (mirror the enum in patch/shuffle.c)
SHUFFLE_SONGS = 0    # every song, stock Shuffle play mode, from a random song
SHUFFLE_ALBUMS = 1   # albums in random order, each album's tracks in order
SHUFFLE_FOLDERS = 2  # folders in random order, each folder's files in order


class Row:
    def __init__(self, label, action, arg=0, rid=None, sub=None, value=None):
        self.label, self.action, self.arg = label, action, arg
        self.rid = rid       # a cards page: the number in the row's widget names (pod_row<rid>) when it is not the row's place among the rows (the Preset page's Edited and Rename rows: the band rows keep their numbers)
        self.sub, self.value = sub, value   # the preset page's Edited row: its static grey line and grey value (a band row's are the payload's)


WIDE_VALUE_ACTIONS = (ACT_PEQ_TCURVE, ACT_PEQ_TPREAMP)   # value rows of the 10-Band editor: the grey value has PREAMP_W (tools/pod_settings.py) so that "Auto · −12.0 dB" and Классическая fit


def row_kind(row):
    """How a settings row is drawn: 'switch', 'value' (a grey value and the chevron), 'check', 'info' (a grey value, no chevron, no touch), 'action' (no accessory) or 'link' (the chevron);
    the editor's 'wvalue' (a wide grey value and the chevron) and 'plain' (a white label alone), the Equalizer page's 'preset' (a check), the Presets page's 'lib' (two lines and a chevron, 60 px) and 'delete' (a red label), the preset page's 'preamp' (a grey value, no touch) and 'band' (two lines, no touch)."""
    if row.action in SWITCH_ACTIONS: return 'switch'
    if row.action == ACT_PEQ_PRESET: return 'preset'
    if row.action == ACT_PEQ_PREAMP: return 'preamp'
    if row.action in (ACT_PEQ_BAND,): return 'band'
    if row.action == ACT_PEQ_LIB: return 'lib'
    if row.action == ACT_PEQ_DELETE: return 'delete'
    if row.action in (ACT_PEQ_TRESET, ACT_PEQ_RENAME, ACT_PEQ_TSAVE): return 'plain'
    if row.action in WIDE_VALUE_ACTIONS: return 'wvalue'
    if row.action in VALUE_ACTIONS or (row.action == ACT_STOCK and STOCK_PAGES[row.arg][1]): return 'value'
    if row.action in CHECK_ACTIONS: return 'check'
    if row.action in (ACT_INFO, ACT_SFDEL): return 'info'
    if row.action in ACTION_ACTIONS or (row.action == ACT_HOME and row.arg == HOME_UPDATE): return 'action'
    return 'link'


class Hdr:
    """A section header of a cards page (grey text above a card)."""
    def __init__(self, text): self.text = text


class Note:
    """A grey note under a card; lines > 1: a wrapping label that tall (the Equalizer page's hint)."""
    def __init__(self, text, lines=1): self.text, self.lines = text, lines


class Sliders:
    """The 10-Band editor's card of ten vertical sliders (a view the payload paints: patch/tenband.c; tools/pod_settings.py SLIDERS_H high)."""


class Graph:
    """The preset page's frequency-response card (a view the payload paints a bitmap into; tools/pod_settings.py GRAPH_H high)."""


class Segment:
    """The band page's Peak / Low shelf / High shelf control (a view the payload paints: patch/peqband.c; tools/pod_settings.py SEG_H high)."""


class HSliders:
    """The band page's card of three horizontal sliders, Frequency, Gain and Q (a view the payload paints; tools/pod_settings.py HSL_H high)."""


GRAPH = Graph()
SLIDERS = Sliders()
SEGMENT = Segment()
HSLIDERS = HSliders()
SLIDER_TEXTS = ('31', '63', '125', '250', '500', '1k', '2k', '4k', '8k', '16k')   # the sliders' frequency labels: numbers, shown as they are in every language (Hz is the graph's unit)
GRAPH_TEXTS = ('+12', '0', '\u221212', '100', '1k', '10k', 'Hz')   # the graph card's labels: numbers and a unit, shown as they are in every language (the payload sets the scale's ends: +18 / +24)
REGION = 'region'   # in the 10-Band editor's layout: a box (REGION_H high) between the graph card and the slider card holding the grey region line pod_region, empty in the asset (patch/tenband.c writes the dragged band's region)
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

    def wrap_notes(self):
        """Bit n set: the page's nth Note (pod_note<n>_t, in layout order) has lines > 1, a plain label whose wrap open_page turns on (patch/m1plus.c)."""
        notes = [x for x in (self.layout or ()) if isinstance(x, Note)]
        assert len(notes) <= 32
        return sum(1 << n for n, x in enumerate(notes) if x.lines > 1)


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
THEME_PAGE_INDEX = 21
ABOUT_PAGE_INDEX = 22
RECORD_PAGE_INDEX = 28
VINYL_WHITE_INDEX = 29
VTHEME_PAGE_INDEX = 30
BG_PAGE_INDEX = 37   # after UPDATE
ACCENT_PAGE_INDEX = 38  # after BG_PAGE
APPEARANCE_PAGE_INDEX = 39  # after ACCENT_PAGE
PULLDOWN_PAGE_INDEX = 40   # before the Radio pages
REGION_PAGE_INDEX = 45   # after the Radio pages and Get Info
PEQ_PAGE_INDEX = 51        # after the Wi-Fi pages
PEQP_PAGE_INDEX = 52       # after PEQ_PAGE
PEQLIB_PAGE_INDEX = 53     # the Presets page
TENBAND_PAGE_INDEX = 54    # the 10-Band editor, then its Curve and Preamp pages
TENCURVE_PAGE_INDEX = 55
TENPREAMP_PAGE_INDEX = 56
AUTOEQ_PAGE_INDEX = 57
PEQBAND_PAGE_INDEX = 58   # the band page
BATTERY_PAGE_INDEX = 59   # Settings > System > Battery, then its Charge Limit picker
CHGLIMIT_PAGE_INDEX = 60
IDLE_PAGE_INDEX = 61      # the Idle Display picker
LOCK_PAGE_INDEX = 62      # the Lock Screen picker
LOCKWALL_PAGE_INDEX = 63  # the Lock Screen's Wallpaper picker
LOCKSTYLE_PAGE_INDEX = 64 # the Lock Screen's Player Style picker
LOCKINFO_PAGE_INDEX = 65  # the Lock Screen's Custom Wallpaper instructions
NEXTALBUM_PAGE_INDEX = 66   # Settings > Playback > Continue Playing picker: the Navidrome pages follow
NDLOGIN_PAGE_INDEX = 67  # the Navidrome Sign In page
NDSERVER_PAGE_INDEX = 68 # the Navidrome Server page
NDROOT_PAGE_INDEX = 69   # the Navidrome root: the last of PAGES
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
    Row('Subsonic', ACT_SUBSONIC),
]
SETTINGS_ID = 18
assert ITEMS[SETTINGS_ID].label == 'Settings'
# The saved menu (/mnt/data/m1plus/home-menu, patch/menu.c) stores these ids, so they are frozen: a new item is
# appended here and to ITEMS; never insert, remove or reorder (that silently remaps a saved menu). Display order
# comes from DEFAULT_MENU and EXTRAS_GROUPS, not from the id.
ITEM_IDS = ('Now Playing', 'Cover Flow', 'Albums', 'Artists', 'Songs', 'Playlists', 'Shuffle', 'Genres', 'Folders',
            'Favorites', 'Recently Added', 'Recently Played', 'Most Played', 'Composers', 'Hi-Res', 'Update Library',
            'Tidal', 'CD Ripper', 'Settings', 'Pod', 'Podcasts', 'Search', 'Radio', 'Subsonic')
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
# Playlists: the stock playlists as a grid, each a mosaic of its albums' covers (patch/playlists.c); the "..." button opens the shared view-sort card.
PLAYLISTS = Page('m1plus_playlists', 'm1plus_playlists_page', 'Playlists', kind='playlists')
# The "..." card's action rows (the shared view-sort card's slots 6..9, tools/pod_ui.py view_sort_card; patch/playlists.c): New Playlist, Import and Export
# run the stock code, Delete Playlists is the page's own select mode. Short labels of our own (the stock "Import playlist" in Spanish would not fit beside the glyph).
PLAYLIST_MENU = ('New Playlist', 'Import', 'Export', 'Delete Playlists')
# Songs: the library as one list (patch/songs.c): a large title, Play / Shuffle pills, sections with a pinned header and the A-Z rail (Title order), the navbar's
# "..." button, whose card is the shared view-sort card (tools/pod_ui.py view_sort_card: Search Songs, Select, Grid / List, the sort rows vs_item0..3; the order is the stock
# sort_flag 0..4, patch/songs.c writes the flag the way the stock dialog's row handler does).
SONGS = Page('m1plus_songs', 'm1plus_songs_page', 'Songs', kind='songs')
FOLDERS_SORT_KEYS = ('Name', 'Date Modified', 'Type', 'Type')   # the Folders page's Sort card (the shared view-sort card, patch/folders.c): rows 0..2; the fourth is hidden
SONGS_SORT_KEYS = ('Title', 'File Name', 'Format', 'Recently Added')   # the Sort card's rows (the shared view-sort card, patch/viewsort.c): sort_flag 0, 1, 2 and 3 / 4 (Recently Added reads Newest First / Oldest First)
SHUFFLE_PAGE = Page('m1plus_shuffle', 'm1plus_shuffle_page', 'Shuffle', rows=[
    Row('Shuffle Songs', ACT_SHUFFLE, SHUFFLE_SONGS),
    Row('Shuffle Albums', ACT_SHUFFLE, SHUFFLE_ALBUMS),
    Row('Shuffle Folders', ACT_SHUFFLE, SHUFFLE_FOLDERS),
])

# Settings (iOS style grouped cards, tools/pod_settings.py places them; the design is tools/preview_settings.py's): the stock Wi-Fi and Bluetooth pages, the M1+ Music pages
# (Home Screen, Library, Now Playing, Keyboards), Playback (EQ, the stock Play Settings list) and System (Display, Appearance, Keyboards, About, the stock
# System Settings list), then Developer. Every "stock page" row is a plain navigator_to of the page stock's own list calls (STOCK_PAGES).
SETTINGS_PAGE = Page('m1plus_settings', 'm1plus_settings_page', 'Settings', layout=[
    Row('Wi-Fi', ACT_STOCK, STOCK_WIFI),
    Row('Bluetooth', ACT_STOCK, STOCK_BLUETOOTH),
    GAP,
    Row('Home Screen', ACT_PAGE, HOMESET_PAGE_INDEX),
    Row('Library', ACT_PAGE, LIBRARY_PAGE_INDEX),
    Row('Now Playing', ACT_PAGE, NPSET_PAGE_INDEX),
    Hdr('Playback'),
    Row('EQ', ACT_PEQ, PEQ_PAGE_INDEX),
    Row('Continue Playing', ACT_NEXTALBUM, NEXTALBUM_PAGE_INDEX),
    Row('All Playback Settings', ACT_HOME, HOME_PLAYSET),
    Hdr('System'),
    Row('Display', ACT_STOCK, STOCK_DISPLAY),
    Row('Appearance', ACT_PAGE, APPEARANCE_PAGE_INDEX),
    Row('Keyboards', ACT_PAGE, KEYBOARDS_PAGE_INDEX),
    Row('Battery', ACT_PAGE, BATTERY_PAGE_INDEX),
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

# Settings > Developer > Cache (patch/homecover.c, docs/modules/settings.md "Cache"): the Covers card holds the cache folder's counts (INFO_CC_*: homecover_stat reads each, an ellipsis until counted), the build's Status and Clear Cover Cache;
# the Track Durations card holds Measured Tracks (INFO_DUR: dur_stat, patch/durations.c) and Clear Track Durations.
INFO_CC_ALBUMS, INFO_CC_COVERS, INFO_CC_NOART, INFO_CC_MISSING, INFO_CC_OLD, INFO_CC_SIZE, INFO_CC_STATUS = range(8, 15)   # (patch/m1plus.c INFO_CC = 8 + the index homecover_stat takes)
INFO_DUR = INFO_CC_STATUS + 47  # patch/m1plus.c INFO_DUR = INFO_SFOLD + 1 (asserted below the Settings Files kinds)
INFO_APHOTOS, INFO_ANONE = INFO_DUR + 1, INFO_DUR + 2   # patch/m1plus.c: the Artist Photos card's counts (homecover_stat 7, 8)
CACHE_PAGE_INDEX = 32   # after ONLINEART (31)
CACHE_PAGE = Page('m1plus_cache', 'm1plus_cache_page', 'Cache', layout=[
    Hdr('Covers'),
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
    Hdr('Artist Photos'),
    Row('Photos', ACT_INFO, INFO_APHOTOS),
    Row('None', ACT_INFO, INFO_ANONE),
    Hdr('Track Durations'),
    Row('Measured Tracks', ACT_INFO, INFO_DUR),
    Row('Clear Track Durations', ACT_CLEARDUR),
])

# The plain list behind the Cache page's No art / Missing rows (patch/covlist.c, docs/modules/settings.md "Cache"): the Albums page's asset without its toggle and Cover Flow button, the title set by the payload.
COVLIST = Page('m1plus_covlist', 'm1plus_covlist_page', 'Missing Covers', kind='covlist')

# Settings > Developer > Tools > Settings Files (patch/setfiles.c, docs/modules/settings.md "Settings Files"): the payload's own files as read when the page opens. The labels are the file names (identifiers, not translated).
# Only the setting files (ACT_SFDEL) are tappable, while present: a tap deletes the file after a confirm. The guard files and the folder stay ACT_INFO (never deleted).
SETTING_FILES = ('albums-view', 'albums-sort', 'artists-sort', 'genres-sort', 'composers-sort', 'songs-sort-rev', 'folders-sort', 'playlists-sort', 'playlists-view', 'recently-added-view', 'coverflow-landscape', 'coverflow-volume-keys', 'cassette-theme', 'vinyl-record', 'vinyl-base', 'nowplaying-idle', 'pod-appearance',
                 'appearance-accent', 'appearance-background', 'lockscreen-layout', 'appearance-index-rail', 'appearance-headers', 'home-recent-albums', 'home-daily-mix', 'home-menu', 'pulldown-tiles', 'keyboard-pinyin', 'podcast-online-search', 'podcast-region',
                 'battery-percentage', 'battery-charge-limit', 'playback-shuffle', 'playback-eq', 'playback-next-album', 'search-history', 'radio-view', 'radio-recent', 'covers-rebuild', 'artists-rebuild', 'wifi-networks')
GUARD_FILES = ('m1plus-start', 'm1plus-run', 'm1plus-bad', 'm1plus-off')
# The files older builds left behind (patch/setfiles.c sf_retired, the same order; each with its .tmp sibling). Unsupported Files counts and lists them and
# Delete Unsupported Files removes them. A renamed setting's old name goes here, never a guard file or a setting above (tests: unsupported_tests).
RETIRED_FILES = ('/mnt/data/m1plus-albums', '/mnt/data/m1plus-playlists', '/mnt/data/m1plus-cfsort', '/mnt/data/m1plus-landscape', '/mnt/data/m1plus-tapetheme',
                 '/mnt/data/m1plus-vinylrec', '/mnt/data/m1plus-vinyltheme', '/mnt/data/m1plus-menu', '/mnt/data/m1plus-recent', '/mnt/data/m1plus-search-recent',
                 '/mnt/data/m1plus-shelf', '/mnt/data/m1plus-daily', '/mnt/data/m1plus-covers-rebuild', '/mnt/data/m1plus-kbzh', '/mnt/data/m1plus-pcsearch',
                 '/mnt/data/m1plus-battpct', '/mnt/data/m1plus-pod-theme', '/mnt/data/m1plus-mix', '/mnt/data/m1plus-mix.art', '/mnt/data/m1plus/recently-played')
FOLDER_LABEL = 'm1plus/'
INFO_SF = INFO_CC_STATUS + 1   # patch/m1plus.c INFO_SF = INFO_CC + 7; row k reads setfiles_stat(k): 4 guard files, the folder, the settings
INFO_SFOLD = INFO_SF + 45      # patch/m1plus.c: the Unsupported Files count (setfiles_old_count), above the setting rows
assert len(GUARD_FILES) + 1 + len(SETTING_FILES) <= INFO_SFOLD - INFO_SF, 'the Settings Files rows reach INFO_SFOLD: raise it here and in patch/m1plus.c'
assert INFO_DUR == INFO_SFOLD + 1, 'INFO_DUR must follow INFO_SFOLD (patch/m1plus.c)'
FILES_PAGE_INDEX = 34   # after COVLIST (33)
FILES_PAGE = Page('m1plus_files', 'm1plus_files_page', 'Settings Files', layout=(
    [Row(f, ACT_INFO, INFO_SF + k) for k, f in enumerate(GUARD_FILES)] + [GAP, Row(FOLDER_LABEL, ACT_INFO, INFO_SF + 4)]
    + [Row(f, ACT_SFDEL, INFO_SF + 5 + k) for k, f in enumerate(SETTING_FILES)]
    + [GAP, Row('Unsupported Files', ACT_SFOLD, INFO_SFOLD), Row('Delete Unsupported Files', ACT_SFDELALL)]))

# Settings > Developer: Startup (the Boot to M1+ Music switch, patch/home.c, and the way out to the stock grid) and the developer's tools. Screenshot: a confirm dialog, then a 5 s
# countdown (cancellable), then the screen is written to the card (patch/shot.c). Reset All Settings (under Reset): a confirm, then every settings file is deleted (restart to apply).
# The stock firmware update page is not linked here (About > Software Update is ours; it stays under All System Settings).
DEVELOPER_PAGE = Page('m1plus_developer', 'm1plus_developer_page', 'Developer', layout=[
    Hdr('Startup'),
    Row('Boot to M1+ Music', ACT_STARTUP),
    Row('Open Shanling Home', ACT_GRID),
    Note('Off: the device starts on Shanling Home'),
    Hdr('Tools'),
    Row('Screenshot', ACT_SHOT),
    Row('Cache', ACT_PAGE, CACHE_PAGE_INDEX),
    Row('Settings Files', ACT_PAGE, FILES_PAGE_INDEX),
    Hdr('Reset'),
    Row('Reset All Settings', ACT_RESETALL),
])

# Settings > Home Screen: the Recent Albums and Daily Mix switches (the shelf and the card of the Home menu), . Then the two pages that arrange the menu (patch/menu.c), and last
# Regenerate Daily Mix in a card of its own, which (with its note, pod_note3)
# is hidden while Daily Mix is off (patch/m1plus.c regen_show: the row and the note).
HOMESET_PAGE = Page('m1plus_homeset', 'm1plus_homeset_page', 'Home Screen', layout=[
    Row('Recent Albums', ACT_SHELF),
    Row('Daily Mix', ACT_DAILY),
    Note('Shown on Home below the menu'),
    Row('Main Menu', ACT_PAGE, MENUCFG_PAGE_INDEX),
    Note('Show, hide and reorder the menu'),
    Row('Extras', ACT_PAGE, EXTRASCFG_PAGE_INDEX),
    Note('Items the menu does not show'),
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
# the same for every language). The items are in five titled groups, in a deliberate order (not alphabetical; the title is the
# group's section header, a non-interactive caption, shown while the group has a row on the page): what plays, the library's
# views, the song collections, the streaming services, the tools. Settings is in none: it is the Extras page's navbar button.
EXTRAS_GROUPS = (
    ('Play', ('Now Playing', 'Shuffle', 'Pod')),
    ('Library', ('Albums', 'Artists', 'Songs', 'Playlists', 'Cover Flow', 'Genres', 'Composers', 'Folders', 'Podcasts', 'Radio', 'Search')),
    ('Collections', ('Favorites', 'Recently Played', 'Recently Added', 'Most Played', 'Hi-Res')),
    ('Streaming', ('Subsonic', 'Tidal')),
    ('Tools', ('Update Library', 'CD Ripper')),
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
# cover again), then the List Navigation card (Index Rail and Section Headers, the A-Z lists of patch/azlist.c), Cover Flow's Landscape switch (the album order is the Albums "..." card's).
LIBRARY_PAGE = Page('m1plus_library', 'm1plus_library_page', 'Library', layout=[
    Row('Update Library', ACT_HOME, HOME_UPDATE),
    Row('Rebuild Covers', ACT_REBUILD),
    Row('Rebuild Artist Photos', ACT_AREBUILD),
    Hdr('List Navigation'),
    Row('Index Rail', ACT_AZRAIL),
    Row('Section Headers', ACT_AZHEAD),
    Note('Songs, Artists, Albums and Radio lists'),
    Hdr('Cover Flow'),
    Row('Landscape', ACT_LANDSCAPE),
    Row('Volume Buttons', ACT_VOLKEYS),
    Note('In Cover Flow, the volume buttons move between albums.', lines=2),
    Hdr('Podcasts'),
    Row('Podcast Discover', ACT_PCSEARCH),
    Row('Podcast Region', ACT_REGION, REGION_PAGE_INDEX),
    Note('Search words are sent to Apple.'),
])
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

# Get Info (patch/songinfo.c, docs/modules/songinfo.md): a track's details, opened from the track rows' "..." sheet.
SONGINFO = Page('m1plus_songinfo', 'm1plus_songinfo_page', 'Get Info', kind='songinfo')

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
    GAP,
    Row('Idle Display', ACT_IDLE, IDLE_PAGE_INDEX),
    Note('Shown after 10 seconds on Now Playing.'),
])
# Settings > Now Playing > Idle Display: the picker (a check on the chosen row). Off is stock's Cover mode switch off (the byte 0xa05aa5, [SYSSET] COVERMODE); the others turn it on and say where the
# timed view goes (patch/bigcover.c idle_set; the destination is /mnt/data/m1plus/nowplaying-idle: "0\n" Album Cover, "1\n" Cassette, "2\n" Vinyl).
IDLE_PAGE = Page('m1plus_idleview', 'm1plus_idleview_page', 'Idle Display', layout=[
    Row('Off', ACT_IDLESET, 0),
    Row('Album Cover', ACT_IDLESET, 1),
    Row('Cassette', ACT_IDLESET, 2),
    Row('Vinyl', ACT_IDLESET, 3),
    Note('Shown after 10 seconds on Now Playing.'),
])
IDLE_VALUES = ('Off', 'Album Cover', 'Cassette', 'Vinyl')   # the value the Idle Display row shows, in the order of the picker's rows
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
# Settings > Library > Podcasts > Podcast Region (patch/pcregion.c, docs/modules/podcasts.md "Region"): the picker, Automatic first (its label is the inferred storefront too, set by the payload) then the storefronts by name, a check on the chosen row.
REGION_PAGE = Page('m1plus_podcastregion', 'm1plus_podcastregion_page', 'Podcast Region', layout=[Row('Automatic', ACT_REGIONSET, 0)] + [Row(n, ACT_REGIONSET, i + 1) for i, n in enumerate(pcregion.NAMES)])
BG_VALUES = ('Black', 'Tinted')   # the value the Background row shows for the saved background 0, 1

# Settings > System > Accent (docs/modules/accent.md): the picker, one row per accent with its round swatch where a row's glyph goes (the image pod_sw<arg>, tools/mod_icons.py) and a check on the
# chosen one. The choice applies at once (patch/palette.c pal_accent_set). ACCENT_VALUES is tools/palette.py ACCENTS in the saved order, as the names the rows show.
ACCENT_VALUES = ('Neutral', 'Red', 'Orange', 'Green', 'Teal', 'Purple', 'Champagne')
ACCENT_PAGE = Page('m1plus_accent', 'm1plus_accent_page', 'Accent', layout=[Row(n, ACT_ACCENTSET, i) for i, n in enumerate(ACCENT_VALUES)])

# Settings > System > Appearance > Lock Screen (patch/lockscreen.c, docs/modules/lockscreen.md): it replaces stock's systemset/screensaver_page (the Display page's Lock Screen row opens this page, tools/pod.py LOCKROW).
# Four cards: Enable (stock's lock screen switch); Wallpaper (our picker) and Show Time (stock's clock switch; our own short label, as the page already says Lock Screen); Player Style (a value row, its picker); and
# the Custom Wallpaper instructions (LOCKINFO_PAGE).
LOCK_PAGE = Page('m1plus_lockscreen', 'm1plus_lockscreen_page', 'Lock Screen', layout=[
    Row('Enable', ACT_LOCKON),
    GAP,
    Row('Wallpaper', ACT_LOCKWP),
    Row('Show Time', ACT_LOCKTIME),
    GAP,
    Row('Player Style', ACT_LOCKSTYLE, LOCKSTYLE_PAGE_INDEX),
    GAP,
    Row('Custom Wallpaper', ACT_LOCKINFO),
])
# The Player Style picker: the two layouts, a check on the chosen row; the choice applies the next time the lock screen opens.
LOCKSTYLE_PAGE = Page('m1plus_lockstyle', 'm1plus_lockstyle_page', 'Player Style', layout=[
    Row('Large Cover', ACT_LOCKSET, 0),
    Row('Mini Player', ACT_LOCKSET, 1),
    Note('Applies the next time the lock screen opens.'),
])
# The Wallpaper picker (patch/lockscreen.c lkwp_*): stock's systemset/screensaver_page wallpaper grid as a page of its own (the Default picture and up to five from /mnt/mmc/lockscreenimage, a mark on the chosen one).
# Built in code by tools/pod_ui.py build_lockwall_page (kind 'lockwall'); the payload binds its widgets by name.
LOCKWALL_PAGE = Page('m1plus_lockwall', 'm1plus_lockwall_page', 'Wallpaper', kind='lockwall')
# The Custom Wallpaper instructions: a Release Notes page (the same asset, tools/pod_ui.py build_relnotes_page, and painter, patch/relnotes.c lockinfo_open): the heading "Add Your Own Pictures" and three paragraphs.
LOCKINFO_PAGE = Page('m1plus_lockinfo', 'm1plus_lockinfo_page', 'Custom Wallpaper', kind='relnotes')

# Settings > System > Appearance: one card with the Background value row (Black or Tinted) and the Accent value row (the accent's name), each opening its picker; then a card with the Lock Screen link row (LOCK_PAGE) and a card
# with the Control Center link row (the pull-down's tiles, PULLDOWN_PAGE).
APPEARANCE_PAGE = Page('m1plus_appearance', 'm1plus_appearance_page', 'Appearance', layout=[Row('Background', ACT_BG, BG_PAGE_INDEX), Row('Accent', ACT_ACCENT, ACCENT_PAGE_INDEX),
                                                                                         GAP, Row('Lock Screen', ACT_PAGE, LOCK_PAGE_INDEX), GAP, Row('Control Center', ACT_PAGE, PULLDOWN_PAGE_INDEX)])

# Settings > System > Battery (patch/charging.c, docs/modules/charging.md): the Charge Limit value row and its note; the picker lists the limits, a check on the chosen one
# (100%, the default, is no limit). The labels are numbers, shown as they are (tools/pod_i18n.py BRANDS).
CHGLIMIT_VALUES = (80, 85, 90, 95, 100)   # patch/charging.h CHG_MIN .. CHG_OFF by CHG_STEP
BATTERY_PAGE = Page('m1plus_battery', 'm1plus_battery_page', 'Battery', layout=[
    Row('Battery Percentage', ACT_BATTPCT),
    Note('The exact charge beside the battery icon'),
    Row('Charge Limit', ACT_CHGLIM, CHGLIMIT_PAGE_INDEX),
    Note('Applies while the player is on'),
])
CHGLIMIT_PAGE = Page('m1plus_chargelimit', 'm1plus_chargelimit_page', 'Charge Limit', layout=[Row(f'{p}%', ACT_CHGLIMSET, p) for p in CHGLIMIT_VALUES] + [Note('Resumes a little below the limit')])

# Settings > Playback > Continue Playing (patch/nextalbum.c, docs/modules/nextalbum.md): Off or Next Albums, a check on the chosen one; Auto Mix is planned as a third (file value '2').
NEXTALBUM_PAGE = Page('m1plus_nextalbum', 'm1plus_nextalbum_page', 'Continue Playing', layout=[Row('Off', ACT_NASET, 0), Row('Next Albums', ACT_NASET, 1),
                                                                                        Note('Plays the next album in the order of Albums, the artist or Cover Flow', lines=2)])

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

# The Wi-Fi page (patch/wifipage.c, docs/modules/wifi.md): the stock Wi-Fi page's list under our navbar; Settings > Wi-Fi (an ACT_STOCK row) opens it, the stock page only where it will not open.
WIFI_PAGE = Page('m1plus_wifi', 'm1plus_wifi_page', 'Wi-Fi', kind='wifi')
# One network's info page (patch/wifipage.c wi_open): opened by a network row's info glyph; the navbar's title is the network's name (the payload sets it).
WIFIINFO_PAGE = Page('m1plus_wifiinfo', 'm1plus_wifiinfo_page', 'Wi-Fi', kind='wifiinfo')
# The password page (patch/wifipage.c wk_open): "Enter Password" for a secured network that is joined for the first time, our keyboard embedded (keyboard_attach, KB_PASSWORD).
WIFIPASS_PAGE = Page('m1plus_wifipass', 'm1plus_wifipass_page', 'Enter Password', kind='wifipass')
# The Other Network flow (patch/wifipage.c wo_open, ws_open): one page for a hidden network (name, security, password; the keyboard embedded, KB_*) and the Security picker it opens.
WIFIOTHER_PAGE = Page('m1plus_wifiother', 'm1plus_wifiother_page', 'Join Wi-Fi Network', kind='wifiother')
WIFISEC_PAGE = Page('m1plus_wifisec', 'm1plus_wifisec_page', 'Security', kind='wifisec')

# PAGES[0] is the entry page.
# Settings > Playback > EQ (patch/peq_ui.c, docs/modules/peq.md): stock's Equalizer switch, the 10-Band EQ (our ten-band curve; its curve's name in grey before the check) and a row per APO / AutoEQ preset in
# /mnt/mmc/EQ, the one that plays checked. A cards page whose rows the payload binds itself (so kind 'peq', no exported rows): the switch in a card of its own, then a card of 10-Band EQ and
# one row per preset (the asset has PQ_ROWS, named and shown by the payload, which also sets each shown row's card piece: peq_items(n) is what it shows), or, with no preset, 10-Band EQ
# alone and the hint as a note under it. The bottom card has two link rows, 10-Band EQ (a grey curve name) and Presets (a grey count).
PEQ_ROWS = 64    # patch/offsets.inc PQ_ROWS (tools/pod_ui.py asserts it)
PEQ_SWITCH, PEQ_TENBAND_PICK, PEQ_PRESET = Row('Equalizer', ACT_PEQ_SWITCH), Row('10-Band EQ', ACT_PEQ_PICK), Row('', ACT_PEQ_PRESET)   # the preset rows have no text in the asset
PEQ_OUTPUT = Note('For Headphones')   # under the switch card: the output this page edits (patch/peqout.c: the payload sets "For Line Out" / "For USB DAC" at run time); the asset's text is the headphone one
PEQ_HINT = Note('Download headphone presets in Presets, or copy APO .txt files into EQ on the card.', lines=3)
DSD_NOTE = Note('EQ is not applied to DSD.')   # the grey note at the end of the Equalizer page and the 10-Band editor
PEQ_TENBAND = Row('Edit 10-Band EQ', ACT_PEQ_TENBAND)   # the bottom card under the picker: this link row (the grey curve name, the chevron: the editor) ...
PEQ_PRESETS = Row('Presets', ACT_PEQ_PRESETS)   # ... and this one (a grey count, the chevron: the Presets page)


def peq_items(n):
    """The page's layout while the card has n presets (what the payload leaves visible): the switch, the picker (10-Band EQ and the presets, or 10-Band EQ and the hint), the bottom card (10-Band EQ, Presets)."""
    return [PEQ_SWITCH, PEQ_OUTPUT, PEQ_TENBAND_PICK] + [PEQ_PRESET] * n + ([PEQ_HINT] if n == 0 else [GAP]) + [PEQ_TENBAND, PEQ_PRESETS, DSD_NOTE]


PEQ_PAGE = Page('m1plus_peq', 'm1plus_peq_page', 'Equalizer', kind='peq')
PEQ_PAGE.layout = [PEQ_SWITCH, PEQ_OUTPUT, PEQ_TENBAND_PICK] + [PEQ_PRESET] * PEQ_ROWS + [PEQ_HINT, GAP, PEQ_TENBAND, PEQ_PRESETS, DSD_NOTE]   # the asset: every row, the hint, then the bottom card (the payload hides the hint or the gap before it, whichever the card does not need)

# The Presets page (patch/peqlib.c, docs/modules/peq.md "Presets page"): Download from AutoEq (a card of its own), then a header AutoEq over the stamped files and a header On Card over the
# others, each file one 60 px row in a card. The asset has PEQ_ROWS slots for each section (the payload names, shows and sets the card pieces of as many as there are; the headers stay hidden
# while their section is empty). Rows are numbered in this order, so slot s is row 1 + s: the AutoEq slots first, then the On Card slots.
PEQLIB_DOWNLOAD = Row('Download from AutoEq', ACT_PEQ_AUTOEQ)
PEQLIB_AUTOEQ, PEQLIB_CARD = Hdr('AutoEq'), Hdr('On Card')
PEQLIB_ROW = Row('', ACT_PEQ_LIB)


def peqlib_items(n_ae=PEQ_ROWS, n_card=PEQ_ROWS):
    """The Presets page's layout: n_ae stamped files, n_card others (what the payload leaves visible; a section with none has no header)."""
    return [PEQLIB_DOWNLOAD, PEQLIB_AUTOEQ] + [PEQLIB_ROW] * n_ae + [PEQLIB_CARD] + [PEQLIB_ROW] * n_card


PEQLIB_PAGE = Page('m1plus_peqlib', 'm1plus_peqlib_page', 'Presets', kind='peqlib')
# The AutoEq download page (patch/autoeq.c, docs/modules/peq.md): Radio's search level's top (the glass Back, the title, the field under the bar), over the AutoEq list; opened from the Presets page's row, no menu row.
AUTOEQ_PAGE = Page('m1plus_autoeq', 'm1plus_autoeq_page', 'AutoEq', kind='autoeq')
PEQLIB_PAGE.layout = peqlib_items()   # the asset: every slot

# The preset page (patch/peqpage.c, docs/modules/peq.md "Preset page"): a preset's frequency response, its preamp and its bands, read only. A cards page the payload fills (kind 'peqpage', no exported
# rows): the graph card, the preamp row (a card of its own), a Bands header and PEQ_BANDS band rows in one card (the asset has them all, hidden; the payload names and shows as many as the preset has and sets
# each shown row's card piece), and the note under the card when the parser skipped lines (hidden otherwise).
PEQP_ROWS = 30   # patch/peq.h PEQ_BANDS (tools/pod_ui.py asserts it)
PEQP_PREAMP, PEQP_BAND, PEQP_HDR = Row('Preamp', ACT_PEQ_PREAMP), Row('', ACT_PEQ_BAND), Hdr('Bands')
PEQP_NOTE = Note('%d lines not supported were skipped.', lines=2)
PEQP_DELETE = Row('Delete Preset', ACT_PEQ_DELETE)   # row PEQP_ROWS + 1: the last of the card of Rename and Delete under the bands and the note, always shown
PEQP_RENAME = Row('Rename Preset', ACT_PEQ_RENAME, rid=PEQP_ROWS + 2)   # above Delete Preset in the same card, always shown


def peqp_items(n, skipped=False):
    """The preset page's layout with n bands (what the payload leaves visible); skipped: the note under the card shows (the space before the Rename / Delete card, which is last), else a gap."""
    return [GRAPH, GAP, PEQP_PREAMP, PEQP_HDR] + [PEQP_BAND] * n + ([PEQP_NOTE] if skipped else [GAP]) + [PEQP_RENAME, PEQP_DELETE]


PEQP_PAGE = Page('m1plus_peqpage', 'm1plus_peqpage_page', 'Equalizer', kind='peqpage')
PEQP_PAGE.layout = [GRAPH, GAP, PEQP_PREAMP, PEQP_HDR] + [PEQP_BAND] * PEQP_ROWS + [PEQP_NOTE, GAP, PEQP_RENAME, PEQP_DELETE]   # the asset: every band row, the note, then the Rename / Delete card (the payload hides the note or the gap before it, whichever the page does not need)

# The band page (patch/peqband.c, docs/modules/peq.md "Preset editing"): one band of the preset page, opened by a band row: the graph card with a ring on the band, the Peak / Low shelf / High shelf control, a card of three
# horizontal sliders (Frequency, Gain, Q: a tap on a value types it) and a hint. The navbar has Previous and Next band under the title "Band N". No rows: the payload binds the views by name.
PEQBAND_HINT = Note('Tap a value to type it exactly.')
PEQBAND_PAGE = Page('m1plus_peqband', 'm1plus_peqband_page', 'Equalizer', kind='peqband')   # (the title is the payload's: Band N)
PEQBAND_PAGE.layout = [GRAPH, SEGMENT, HSLIDERS, PEQBAND_HINT]
BAND_SEG_KEYS = ('Peak', 'Low shelf', 'High shelf')   # the control's three labels, in the order of peq_band.type 0 .. 2 (the preset page's keys: the Peak / Low shelf / High shelf forms)
BAND_ROW_KEYS = ('Frequency', 'Gain', 'Q')            # the sliders' labels (Q is the same everywhere)

# The 10-Band editor (patch/tenband.c, docs/modules/peq.md "10-Band EQ"), opened by the Equalizer page's 10-Band EQ link row: a Curve row card (a grey curve name, the chevron: the Curve page) at the top, the graph card (the preset page's),
# the region line's box (REGION), the card of ten sliders (a view the payload paints and handles the touch of), then one card with Preamp (grey "Auto · -5.0 dB" or "-3 dB", the chevron: the Preamp page) and Reset (white, plain). Rows are numbered in this order:
# pod_row0 Curve, pod_row1 Preamp, pod_row2 Reset. No exported rows: the payload binds them itself.
TB_CURVE, TB_PREAMP, TB_RESET = Row('Curve', ACT_PEQ_TCURVE), Row('Preamp', ACT_PEQ_TPREAMP), Row('Reset', ACT_PEQ_TRESET)
TB_SAVE = Row('Save as Preset', ACT_PEQ_TSAVE)   # rid 3 by place (pod_row3): its own card under the Preamp and Reset card, above the DSD note
TENBAND_PAGE = Page('m1plus_tenband', 'm1plus_tenband_page', '10-Band EQ', kind='tenband')
TENBAND_PAGE.layout = [TB_CURVE, GAP, GRAPH, REGION, SLIDERS, GAP, TB_PREAMP, TB_RESET, GAP, TB_SAVE, DSD_NOTE]
# The Curve page: one card, the ten curves in the record's order (PEQ_FLAT .. PEQ_CUSTOM), a check on the current one (arg = the curve id).
TENCURVE_NAMES = ('Flat', 'Pop', 'Rock', 'Dance', 'Blues', 'Metal', 'Vocal', 'Classical', 'Jazz', 'Custom')
TENCURVE_PAGE = Page('m1plus_tencurve', 'm1plus_tencurve_page', 'Curve', kind='tencurve')
TENCURVE_PAGE.layout = [Row(n, ACT_PEQ_CPICK, i) for i, n in enumerate(TENCURVE_NAMES)]
# The Preamp page: Auto (its grey value the cut Auto makes now) in a card of its own with the grey note about it under it, then a card of 0 dB .. -12 dB (the payload writes the texts: "%d dB" with U+2212 before a cut);
# row 0 is Auto, row 1 + n is -n dB (the rows are numbered across both cards).
TENPREAMP_STEPS = 13   # patch/peq.h PEQ_GAIN_MAX + 1: 0 .. -12 dB
TENPREAMP_PAGE = Page('m1plus_tenpreamp', 'm1plus_tenpreamp_page', 'Preamp', kind='tenpreamp')
TENPREAMP_PAGE.layout = [Row('Auto', ACT_PEQ_PAUTO), Note('Auto reduces the level to help prevent distortion from EQ boosts.', lines=2)] + [Row('', ACT_PEQ_PVAL, n) for n in range(TENPREAMP_STEPS)]   # the note's space is the gap between the cards

# The Navidrome root page (patch/ndroot.c, tools/pod_nd.py): the menu rows, the Server row, the footer and the shared empty state. It binds its own rows, so it is not a cards page (no rows for patch/m1plus.c).
NDROOT_PAGE = Page('m1plus_ndroot', 'm1plus_ndroot_page', 'Subsonic', kind='ndroot')

# The Navidrome Server page (patch/ndserver.c, tools/pod_ndserver.py): two cards of the Settings look, the login's three fields and Sync Now / Sign Out. It binds its own rows, so it is not a cards page
# (no rows for patch/m1plus.c): `layout` is only the asset's.
NDSERVER_PAGE = Page('m1plus_ndserver', 'm1plus_ndserver_page', 'Server', kind='ndserver')
NDSERVER_PAGE.layout = [Row('Server URL', ACT_NDVALUE, 0), Row('Username', ACT_NDVALUE, 1), Row('Password', ACT_NDVALUE, 2), GAP, Row('Sync Now', ACT_NDACT, 3), Row('Sign Out', ACT_NDACT, 4)]

# The Navidrome Sign In page (patch/ndserver.c nl_open, tools/pod_ndserver.py build_login): the Server page's three login rows with our keyboard embedded, as the Join Wi-Fi Network page.
NDLOGIN_PAGE = Page('m1plus_ndlogin', 'm1plus_ndlogin_page', 'Sign In', kind='ndlogin')

# PAGES[0] is the entry page.
PAGES = [MENU, COVER, ARTISTS, SHUFFLE_PAGE, SETTINGS_PAGE, EXTRAS_PAGE, ALBUMS, MENUCFG_PAGE, LIBRARY_PAGE, HOMESET_PAGE, PLAYLISTS, SONGS, DAILYMIX,
         EXTRASCFG_PAGE, DEVELOPER_PAGE, IPOD, PODCASTS, TAPE, NPSET_PAGE, KEYBOARD, KEYBOARDS_PAGE, THEME_PAGE, ABOUT_PAGE, SEARCH, ALBUM_PAGE, VINYL, FOLDERS, QUEUE_PAGE,
         RECORD_PAGE, VINYL_WHITE, VTHEME_PAGE, ONLINEART, CACHE_PAGE, COVLIST, FILES_PAGE, UPDATE, RELNOTES, BG_PAGE, ACCENT_PAGE, APPEARANCE_PAGE, PULLDOWN_PAGE, RADIO, RADIONP, RADIOINFO, SONGINFO, REGION_PAGE, WIFI_PAGE, WIFIINFO_PAGE, WIFIPASS_PAGE, WIFIOTHER_PAGE, WIFISEC_PAGE,
         PEQ_PAGE, PEQP_PAGE, PEQLIB_PAGE, TENBAND_PAGE, TENCURVE_PAGE, TENPREAMP_PAGE, AUTOEQ_PAGE, PEQBAND_PAGE, BATTERY_PAGE, CHGLIMIT_PAGE, IDLE_PAGE, LOCK_PAGE, LOCKWALL_PAGE, LOCKSTYLE_PAGE, LOCKINFO_PAGE, NEXTALBUM_PAGE, NDLOGIN_PAGE, NDSERVER_PAGE, NDROOT_PAGE]
assert PAGES[KEYBOARDS_PAGE_INDEX] is KEYBOARDS_PAGE
assert PAGES[NPSET_PAGE_INDEX] is NPSET_PAGE
assert PAGES[SHUFFLE_PAGE_INDEX] is SHUFFLE_PAGE and PAGES[SETTINGS_PAGE_INDEX] is SETTINGS_PAGE
assert PAGES[EXTRASCFG_PAGE_INDEX] is EXTRASCFG_PAGE and PAGES[DEVELOPER_PAGE_INDEX] is DEVELOPER_PAGE
assert PAGES[EXTRAS_PAGE_INDEX] is EXTRAS_PAGE and PAGES[MENUCFG_PAGE_INDEX] is MENUCFG_PAGE
assert PAGES[LIBRARY_PAGE_INDEX] is LIBRARY_PAGE and PAGES[HOMESET_PAGE_INDEX] is HOMESET_PAGE
assert PAGES[ABOUT_PAGE_INDEX] is ABOUT_PAGE and PAGES[RECORD_PAGE_INDEX] is RECORD_PAGE and PAGES[BG_PAGE_INDEX] is BG_PAGE and PAGES[ACCENT_PAGE_INDEX] is ACCENT_PAGE and PAGES[APPEARANCE_PAGE_INDEX] is APPEARANCE_PAGE and PAGES[PEQ_PAGE_INDEX] is PEQ_PAGE and PAGES[PEQP_PAGE_INDEX] is PEQP_PAGE and PAGES[PEQLIB_PAGE_INDEX] is PEQLIB_PAGE
assert PAGES[TENBAND_PAGE_INDEX] is TENBAND_PAGE and PAGES[TENCURVE_PAGE_INDEX] is TENCURVE_PAGE and PAGES[TENPREAMP_PAGE_INDEX] is TENPREAMP_PAGE and PAGES[AUTOEQ_PAGE_INDEX] is AUTOEQ_PAGE and PAGES[PEQBAND_PAGE_INDEX] is PEQBAND_PAGE
assert PAGES[VINYL_WHITE_INDEX] is VINYL_WHITE and PAGES[VTHEME_PAGE_INDEX] is VTHEME_PAGE and PAGES[CACHE_PAGE_INDEX] is CACHE_PAGE and PAGES[FILES_PAGE_INDEX] is FILES_PAGE
assert PAGES[PULLDOWN_PAGE_INDEX] is PULLDOWN_PAGE and PAGES[REGION_PAGE_INDEX] is REGION_PAGE
assert PAGES[BATTERY_PAGE_INDEX] is BATTERY_PAGE and PAGES[CHGLIMIT_PAGE_INDEX] is CHGLIMIT_PAGE and PAGES[LOCK_PAGE_INDEX] is LOCK_PAGE and PAGES[LOCKWALL_PAGE_INDEX] is LOCKWALL_PAGE and PAGES[LOCKSTYLE_PAGE_INDEX] is LOCKSTYLE_PAGE and PAGES[LOCKINFO_PAGE_INDEX] is LOCKINFO_PAGE 
assert PAGES[IDLE_PAGE_INDEX] is IDLE_PAGE
assert PAGES[NEXTALBUM_PAGE_INDEX] is NEXTALBUM_PAGE and NEXTALBUM_PAGE_INDEX == PAGES.index(NDLOGIN_PAGE) - 1
assert PAGES[NDLOGIN_PAGE_INDEX] is NDLOGIN_PAGE and PAGES[NDSERVER_PAGE_INDEX] is NDSERVER_PAGE and PAGES[NDROOT_PAGE_INDEX] is NDROOT_PAGE and NDROOT_PAGE_INDEX == len(PAGES) - 1
assert PAGES[THEME_PAGE_INDEX] is THEME_PAGE
