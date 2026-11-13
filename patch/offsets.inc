/* Stock M1 Plus V2.1 layout and ABI constants shared by patch/m1plus.c and test/patch.py.
 * The test harness parses the #defines in this file, so a change cannot leave the mocks behind.
 * Structure follows q2-pod's patch/offsets.inc; the values are the M1 Plus's own, read from demo
 * with tools/disasm.py. */
#define W_NAME 0x10       /* widget_t name; the Home dispatcher reads only this: lw $a0, 0x10($a0) @0x533ba4 */
#define EVT_CLICK 0x10c   /* Home icons register their click with this type: widget_on @0x533f78 */
#define RET_OK 0
#define RET_STOP 11       /* an emitter handler's result that ends the dispatch: no older handler runs (emitter_dispatch cmp 0xb @0x6f450c) */
#define HOME_IDS 18       /* the Home dispatcher's jump table covers 0..17: sltiu $v1, $v0, 0x12 @0x533ba8 */
/* Home item ids (config.ini [MAIN] HOMEMENU; names from the table at 0x97c940, get_homemenu_showinfo).
 * Which ids reach Home is decided by reset_homemenu_index/load_home_menu: id 0 only when the
 * `language` global (0xa05ab8) is 0 (Simplified Chinese); every other id comes from the saved
 * HOMEMENU list, which the user can edit in the Home customisation dialog. See docs/architecture.md. */
/* 0 hifi/hifimusic_page (Simplified Chinese only)   1 tidal/tidal_main        2 systemset/updatemusic_page
 * 3 allmusic_page 0xf001: all songs                  4 folder_page            5 album_page, context {0xf003, 0}
 * 6 localclass_page 0xf004: artists                  7 localclass_page 0xf006: genres   8 0xf005: composers
 * 9 allmusic_page 0xf002: hi-res   10 0xf00a: favourites   11 0xf008: most played   12 0xf007: recently played
 * 13 0xf009: recently added        14 playlist_page   15 cdripper_page (sets GPIO PA11 first)
 * 16 playset/playset_page          17 systemset/sysset_page.  The ids tools/pod_pages.py uses are the same. */
#define HOME_ALBUM 5

/* The Home grid, as the stock page builder 0x534064 / icon builder 0x533d8c lay it out (patch/home.c adds one
 * icon the same way): a slide_view "home_sview" of 320x364 page views, six icons each in two columns and three
 * rows; an icon is a 154x118 view holding a 66x66 clickable image (named by the decimal id, EVT_CLICK ->
 * 0x533b80 with the image as ctx, style home_<name>_style) and a 154x36 label at y 92. */
#define ICONS_PER_PAGE 6    /* the icon builder's loop: slt/bne on 6 @0x5340/0x53401c */
#define ICON_W 154          /* view_create(.., 0x9a, 0x76) @0x533e18 */
#define ICON_H 118
#define ICON_X0 6           /* column 0; column 1 is ICON_X0 + ICON_W (0x9a added @0x534010) */
#define ICON_IMG_X 44       /* image_create(cell, 0x2c, 0x14, 0x42, 0x42) @0x533e88 */
#define ICON_IMG_Y 20
#define ICON_IMG 66
#define ICON_LABEL_Y 92     /* label_create(cell, 0, 0x5c, 0x9a, 0x24) @0x533f8c */
#define ICON_LABEL_H 36
#define PAGE_W 320          /* view_create(sview, 0, 0, 0x140, 0x16c) @0x534168 */
#define PAGE_H 364
/* the pod menu as the Home instance (no navbar): the list takes the whole 450 px window */
#define SCREEN_W 320
#define WIN_H 450
#define HOME_PAD 10        /* the Home instance of the pod menu keeps this much air above its first row and below its last (patch/home.c hm_fill_window) */
/* the cache pill of the Home instance (patch/homecover.c, tools/pod_ui.py cache_pill): a capsule HC_W x HC_PH at (HC_X, HC_Y) above the list while covers are built or tracks measured; the list then starts HC_H lower (the pill and 8 px of air).
 * Inside it (pill coordinates): the 15 px text, a HC_BH px progress bar HC_BW wide under it (the fill is resized to done/total, at least HC_BH), and the stop button (a HC_XW px square touch box at HC_XX, HC_XY, drawing the 28 px disc pod_cache_x centred) */
#define HC_X 12
#define HC_Y 10
#define HC_W 296
#define HC_PH 40
#define HC_H 48
#define HC_PX 15
#define HC_TX 18
#define HC_TY 5
#define HC_TH 18
#define HC_BW 230
#define HC_BY 26
#define HC_BH 4
#define HC_XX 256
#define HC_XY 0
#define HC_XW 40

/* ---------------------------------------------------------------------------
 * Cover Flow (patch/coverflow.c). Event ids, record layout and widget fields
 * read from this demo with tools/disasm.py; the geometry is this project's own
 * (320x480 portrait), the depth model follows q2-pod (docs/architecture.md).
 */
#define EVT_DESTROY 0x0c        /* widget_destroy_sync: event_init(e, 0xc) @0x670600 */
#define EVT_AFTER_PAINT 0x120   /* widget_paint dispatches it after children+border @0x66de3c */
#define EVT_VALUE_CHANGED 0x11c /* slide_menu commit dispatches 0x11b then 0x11c @0x61213c */
#define EVT_VALUE_CHANGING 0x11d /* a slider while it is dragged: stock's brightness page binds 0x11d and 0x11c (tools/pod.py LOCKSCREEN_PINS) */

/* stSongInfo record fields (getAllAlbum's row callback @0x4e93c8, loadSongList @0x4e2ce0) */
#define REC_ID 0x00        /* -1 = the "Unknown Album" row getAllAlbum appends */
#define REC_NAME 0x08      /* file name; loadSongList matches a track by it */
#define REC_PATH 0x0c      /* fileurl: for an album row, its first track */
#define REC_TITLE 0x10     /* tag title (album rows carry the album name here too) */
#define REC_ALBUM 0x14
#define REC_ARTIST 0x18
#define REC_TYPE 0x34      /* 8 song, 4 directory/class row */
#define REC_CUE_START 0x48 /* loadSongList's third argument */

/* Stock library/browsing state (all pinned in tools/pod.py DATA) */
#define CLASS_ALBUMS 0xf003   /* loadLocalClassList: getAllAlbum into *pdeq_showlist */
#define CLASS_ALBUM_TRACKS 0xff10 /* what loadAlbumdetailList(0xf003, row) leaves in classinfo[0] */
#define PLAY_MODE 2           /* playing_page context mode, as album_page/albuminfo_page pass */

/* Artists (patch/artists.c, the scoped Cover Flow). loadLocalClassList(0xf004) runs
 * GetAllAlbumArtist when the artist_type global (0xa05a14, PLAYSET ARTISTTYPE, read by config_init
 * @0x4e52d0) is 1, else getAllArtist (@0x4ee6e8); both rows carry the name in REC_TITLE (row
 * callbacks 0x4e95b8 / 0x4e9724), which the stock Artists rows show (@0x535dec). A tap there opens
 * album_page {0xf004, row} (@0x535d40), whose loadAlbumList(0xf004, row) (0x4ee8d8) stores the
 * artist in classinfo_save and loads its albums with class 0xff01 (getAlbumByAlbumArtist /
 * getAlbumByArtist, @0x4ee7cc); an album row then goes through loadAlbumdetailList(0xff01, row),
 * which leaves 0xff11 (getMusicByAlbumAnd[Album]Songer, @0x4ee858) in classinfo[0]. */
#define CLASS_ARTISTS 0xf004
#define CLASS_ARTIST_ALBUMS 0xff01
#define CLASS_ARTIST_SONGS 0xff11   /* what loadAlbumdetailList(0xff01, the All songs row) leaves in classinfo[0]: every song of the artist (patch/songs.c) */
#define CLASSINFO_SIZE 0x390        /* the browsing record loadAlbumList memsets (@0x4ee8d8): the artist list's whole state, which every other query overwrites */
#define ID_ALL_SONGS -2    /* REC_ID of the "All songs" row getAlbumByArtist appends last (@0x4eae30); its tracks are all the artist's songs (classinfo[8] = 1, @0x4eebec) */

/* Cover Flow geometry, 320x480 portrait: a CF_VIEW_W x CF_VIEW_H frame under the 50 px navbar.
 * The centre cover is ART_SIZE square with its top CF_TOP below the frame's; side covers turn
 * CF_TURN (60 degrees) inward (the sine table in coverflow.c), sit CF_X1 px from the centre and then CF_XS
 * apart, CF_Z1 and then CF_ZS px further back, seen from CF_EYE px. Brightness (of 256) is 256 at
 * the centre, CF_BRIGHT1 one out, CF_BRIGHT2 two out, 0 three out. Each cover reflects CF_REFLECT
 * px at native size from CF_REFLECT_TOP (of 256) of its brightness down to black. */
#define ART_SIZE 168
#define CF_VIEW_W 320
#define CF_VIEW_H 276
#define CF_CX 160          /* the centre line, between columns 159 and 160 */
#define CF_TOP 31
#define CF_EYE 312
#define CF_X1 110
#define CF_XS 48
#define CF_Z1 96
#define CF_ZS 22
#define CF_BRIGHT1 192
#define CF_BRIGHT2 128
#define CF_TURN 16 /* side covers turn 16 x 3.75 = 60 degrees (cfg_t.turn) */
#define CF_REFLECT 26
#define CF_REFLECT_TOP 64
/* The iPod page's Cover Flow screen (patch/ipod_cf.c, docs/modules/ipod-coverflow.md): the same depth renderer with numbers tuned to a photo of an iPod classic, for the 320 x 240 screen under the title bar:
 * a 320 x IPCF_FRAME_H frame on white (IPCF_BG; r | g << 8 | b << 16) drawn at y IPCF_FRAME_Y (= IP_BAR_H), the centre cover IPCF_ART px at IPCF_TOP, seen from IPCF_EYE, the first side cover IPCF_X1 out and IPCF_Z1 back, the rest IPCF_XS / IPCF_ZS
 * apart; IPCF_REFLECT px of reflection; the covers dim lightly to IPCF_TAIL of 256 three out, then fade out by 3.5 (seven covers show). The two caption lines start at IPCF_CAP_Y, IPCF_CAP_H high each. The
 * slide eases to the target album: each IPCF_FRAME_MS tick covers dt / (dt + IPCF_TAU_MS) of what is left, ends within IPCF_DONE (1/64 album), and never starts more than
 * IPCF_NEAR albums away (a long jump lands near the target at once, so the covers that show are the ones being decoded). */
#define IPCF_FRAME_Y 24
#define IPCF_FRAME_H 192
#define IPCF_BG 0xffffff
#define IPCF_ART 128
#define IPCF_TOP 18
#define IPCF_EYE 272
#define IPCF_X1 84
#define IPCF_XS 34
#define IPCF_Z1 62
#define IPCF_ZS 6
#define IPCF_REFLECT 40
#define IPCF_TAIL 208
#define IPCF_TURN 20 /* 75 degrees: the iPod's side covers turn further than the page's */
#define IPCF_CAP_Y 192
#define IPCF_CAP_H 22
#define IPCF_FRAME_MS 33
#define IPCF_TAU_MS 70
#define IPCF_DONE 1024
#define IPCF_NEAR 4
#define DRAG_PX 108        /* finger travel per album */
#define TAP_SLOP 12        /* px either way: a release within this of the down point (and no drag) is a tap */
#define DRAG_START 5       /* px along the carousel, and no more across, start a drag (counted from there); tune on the device */
#define FLING_MS 120       /* the fling coasts for this long at the release velocity */
#define FLING_WINDOW 80    /* ms of samples the velocity is taken over; none in it but the release, no fling */
#define SNAP_MS 16         /* the snap animation's timer period */
#define OVER_NUM 2          /* the rubber band's ceiling past an end: OVER_NUM / OVER_DEN of a cover (patch/coverflow.c rubber) */
#define OVER_DEN 5
#define SNAP_BASE_MS 120   /* an ease takes this plus SNAP_ALBUM_MS per album of travel, at most SNAP_MAX_MS */
#define SNAP_ALBUM_MS 60
#define SNAP_MAX_MS 360
#define FNV_SEED 2166136261u

/* Cover Flow landscape (patch/coverflow.c, docs/ui.md): the same depth renderer into the 320 x 400 body under
 * the navbar (which stays, Back, toggle and Now Playing working as in portrait), its bitmap rotated a quarter
 * turn, so the carousel runs along the 400 px side. A logical landscape frame CFL_W x CFL_H (x right, y down as
 * the user sees it, the content turned 90 degrees clockwise on the screen, the device held turned
 * counter-clockwise): logical (x, y) is physical (CFL_H - 1 - y, x), CFL_Y px down the window. The centre cover is
 * the 168 px texture 1:1 like portrait's and the eye, depth and reflection are portrait's; the side covers are
 * spread wider (CFL_X1, CFL_XS). The captions are drawn into the frame with the page's font (the glyphs turned by
 * the same map) in the CFL_CAP_W px under the reflections. */
#define CFL_Y 50           /* the frame's top in the window: under the 50 px navbar */
#define CFL_W 400          /* the window's 450 px less the navbar */
#define CFL_H 320
#define CFL_CX 200
#define CFL_TOP 28
#define CFL_X1 160
#define CFL_XS 84
#define CFL_DRAG_PX 132    /* finger travel per album */
#define CFL_ALBUM_Y 244    /* the caption lines' tops (logical), the album's 22 px, the artist's 18 px */
#define CFL_ARTIST_Y 274
#define CFL_CAP_W 368      /* 16 px margins, as portrait's captions */
#define CANVAS_FONT_SIZE 0x0c   /* canvas_t: font_size u16 @0xc, font_t * @0x34 (canvas_draw_text @0x645348 reads both) */
#define CANVAS_FONT 0x34
#define GLYPH_FORMAT_ALPHA 0    /* glyph_t: x,y s16, w,h,advance u16 @0..9, format u8 @0xa (0 = 8 bit alpha, rows w bytes), pitch u8, data @0xc */

/* Pointer events (Cover Flow's touch layer, the Albums grid) */
#define EVT_KEY_DOWN 0x10f      /* widget_on_keydown tests 0x10f @0x670974; 0x110 is KEY_LONG_PRESS (@0x6a497c), not KEY_DOWN */
#define EVT_KEY_UP 0x113        /* home_page_init binds on_wm_keyup_fun 0x4cd9ac with it (@0x534fbc); dialog_volume_dialog_init binds its window handler 0x47e330 (@0x47e494) */
#define EV_KEY 0x18             /* the key event's code: on_wm_keyup_fun reads 0x18($a1) (0x4cda0c) */
#define KEY_VOL_UP 0xdc         /* on_wm_keyup_fun, the volume dialog handler 0x47e330 */
#define KEY_VOL_DOWN 0xdd
#define EVT_POINTER_DOWN 0xff  /* input_device_status_on_input_event jump table @0x88f120 */
#define EVT_POINTER_MOVE 0x101
#define EVT_POINTER_UP 0x103
#define EVT_POINTER_ABORT 0x107 /* widget_on_pointer_up/move dispatch it @0x6719b8 */
#define PE_X 0x18               /* pointer_event_t: x, y (screen coordinates, widget_to_local turns them local); event_t.time u64 @0x8 */
#define PE_Y 0x1c
#define EV_TIME 0x08

/* AWTK ABI used by the Cover Flow renderer (all read from this demo) */
#define EVENT_PAINT_CANVAS 0x18 /* paint_event_t.canvas: paint_event_init stores a3 there @0x65026c */
#define BITMAP_FLAGS 0x0c       /* bitmap_t: w@0, h@4, flags u16@0xc, format u16@0xe, data@0x14 */
#define BITMAP_FORMAT 0x0e      /*   (bitmap_create_ex @0x6400d4: sw w,0; sw h,4; sh fmt,0xe) */
#define BITMAP_RGBA8888 1       /* bitmap_format_t: 1 RGBA8888, 2 ABGR, 3 BGRA, 4 ARGB */
#define BITMAP_RGBA_AT { { 0, 1, 2, 3 }, { 3, 2, 1, 0 }, { 2, 1, 0, 3 }, { 1, 2, 3, 0 } }
#define IMAGE_SCALE_AUTO 4      /* image_draw_type_t, as the stock cover rows use */
#define IMAGE_DRAW_CENTER 2     /* centred at its own size (DEFAULT 0, ICON 1, CENTER 2, SCALE 3, SCALE_AUTO 4) */

/* Cover Flow page geometry (the ui/m1plus_cover.bin asset must match; tools/pod_ui.py) */
#define CF_COVER_Y 89      /* view_covers' y in the window (NAVBAR_H + 39) */

/* ---------------------------------------------------------------------------
 * Shuffle (patch/shuffle.c, docs/architecture.md). Read from this demo with tools/disasm.py.
 */
#define REC_SIZE 0x58      /* stSongInfo: memset(local, 0, 0x58) in loadSongList @0x4e2e4c and the row callback @0x4e908c */
#define REC_CLASS 0x38     /* loadSongList stores its class argument here in every copy @0x4e3144 */
#define REC_TRACK 0x3c     /* atoi(track) @0x4e9304 (column 10 of songtable) */
#define REC_DISC 0x40      /* atoi(cd_num) @0x4e9318 (column 11); getMusicByAlbum sorts by disc, then track (0x4e9020) */
#define CLASS_ALL_SONGS 0xf001 /* loadLocalClassList: getAllMusic into *pdeq_showlist (@0x4ee5bc), the Songs page's class */
/* mclGetPlayMode/mclSetPlayMode values: Now Playing's mode button cycles 0..3 and styles them
 * btn_imgorder / btn_imgcycle1 / btn_imgrandom / btn_imgcycle (@0x5398cc..0x539948) */
#define MODE_ORDER 0       /* list play: stops after the last track (mclNextSong @0x5d5950) */
#define MODE_REPEAT_ONE 1
#define MODE_SHUFFLE 2     /* mclNextSong draws from the unplayed-index pool mclLoadPlayList fills (@0x5d1fe0, 0x5d03b0) */
#define MODE_REPEAT_ALL 3
#define MSGINFO_KIND 1     /* dialog/msginfo_dialog context {kind, ms, text[0x200], text2[0x200]}: kind 1 one white line (@0x4786f8) */
#define MSGINFO_MS 2000    /* as the stock "file not found" toast @0x525a04 */
#define MSGINFO_TEXT 0x200
#define CONFIRM_KIND_WRAP 5 /* dialog/confirminfo_dialog context, same layout: kind 5 = a centred white 20 px word-wrapped label (260 x 80 at y 25, @0x472e1c), text at +8 */
#define CONFIRM_YES 0xa     /* navigator_to_with_context returns this for the Yes button (btn_enter); the call is modal (on_eqreset_onclick @0x49dd6c) */
#define SHUFFLE_MAX 65536  /* Shuffle Albums/Folders sort an index of at most this many songs (q2-pod QUEUE_LIMIT) */

/* ---------------------------------------------------------------------------
 * Library rows (patch/rows.c, patch/rows.json, docs/architecture.md). The row fit follows q2-pod's
 * compact_row_layout (patch/navigation.c); the ABI is this demo's (tools/disasm.py).
 */
#define W_X 0x00                /* widget_t x, y, w, h: widget_move_resize_ex stores them @0x66d268 */
#define W_Y 0x04
#define W_W 0x08
#define W_H 0x0c
#define W_PARENT 0x44           /* widget_t parent: widget_restack reads it, lw $v0, 0x44($a0) @0x66a014 */
#define W_CHILDREN_LAYOUT 0x64  /* widget_set_children_layout: sw $v0, 0x64($s0) @0x657014 */
#define W_VT 0x70               /* widget_t vtable: widget_paint reads it, lw $v0, 0x70($s0) @0x66dd6c */
#define SV_PAINT_CHILDREN 0xf4  /* scroll_view_t paint-children hook: scroll_view_on_paint_children calls it (lw $t9, 0xf4($s3) @0x610ed0), list_view stores 0x60c164 (sw @0x60cd10) */
#define LAYOUT_VTABLE 0x0c      /* children_layouter_t: str_t params (12 bytes), then the vtable */
#define LAYOUT_X_MARGIN 0x14    /* children_layouter_default_t u8s, read by its layout @0x63a5a0 */
#define LAYOUT_SPACING 0x16
#define DEFAULT_LAYOUT_VTABLE 0x904924u /* children_layouter_default_create stores it @0x63af28 */
#define DEFAULT_LAYOUT_FN 0x63a444u     /* its slot 2, the layout (children_layouter_default_layout) */
#define LAYOUT_VTABLE_WORDS 8   /* type, to_string, layout, get_param, set_param, destroy, is_valid, clone */
#define LAYOUT_SLOT 2
#define ROW_RIGHT 12            /* a row's text ends this far from its right edge (the x=12 rows' margin) */
#define ROW_ART 52              /* the album cover (rows.json ART): 1:1 thumbnails */
#define ROW_ART_INSET 4         /* the cover's left inset on x=0 rows */
#define ROW_SEPARATOR 4         /* list_item_style draws a 4 px separator under each list_item row */
#define ROW_MARKER_IMAGE "np_row_playing"   /* the playing row's marker: 40 x 20, a 20 px wave at its right end (tools/mod_icons.py NP) */
#define ROW_NUM_W 24           /* the album page's number column (patch/albumpage.c): every digit is 11 px at the list title size (LIST_TITLE_PX 21) by AWTK's metrics, "99" = 22 */
#define ROW_NUM_W3 34          /* the column of a 3-digit number (a 100+ track album): "999" = 33 */
#define ROW_MAX_CHILDREN 16   /* the row fit leaves anything with more children to the stock layout */


/* ---------------------------------------------------------------------------
 * The album page's numbers (patch/albumpage.c, docs/modules/album-page.md; ui/m1plus_album.bin and the Podcasts Show level read them).
 * REC_YEAR: songtable's column 9 (`year`), which the row callback @0x4e908c atoi()s into the stack record at +0x30; the insert
 * (@0x5edfc4) writes it from taglib_tag_year. There is no duration column (time / time_end are CUE offsets, 0 for ordinary files,
 * @0x5edb88): the page's total comes from the durations table (patch/durations.c). CLASSINFO_ALL_SONGS: the byte loadAlbumdetailList sets in the browsing record for the stock
 * All songs row (0xff01, @0x4eebec).
 * Geometry in the window (320 wide, the lines centred on x 160): the cover AH_ART square at (AH_ART_X, AH_ART_Y) with its four AH_CORNER px
 * corners cut; the title, artist and "year . N tracks" lines centred in AH_TEXT_W; the round Shuffle (AH_SHUF_W) and the Play
 * pill (AH_PLAY_W) centred as a pair; the track rows follow at AH_HDR_H. The list starts at the window's top (the glass controls
 * sit over it), so the header's first rows are padding.
 */
#define REC_YEAR 0x30
#define CLASSINFO_ALL_SONGS 8
#define AH_ART 160
#define AH_ART_X 80
#define AH_ART_Y 50
#define AH_CORNER 10
#define AH_TEXT_X 17
#define AH_TEXT_W 286
/* vertical rhythm (tools/ah_ink.py, measured ink): cover bottom -> title capitals 16, title baseline -> artist capitals 9,
 * artist baseline -> year digits 9, year baseline -> pill top 16; the label rects are their font size high */
#define AH_TITLE_Y 224
#define AH_TITLE_H 22
#define AH_ARTIST_Y 247
#define AH_ARTIST_H 18
#define AH_META_Y 267
#define AH_META_H 15
#define AH_BTN_Y 292
#define AH_BTN_H 44
#define AH_SHUF_X 42
#define AH_SHUF_W 44
#define AH_DISC 40              /* the Shuffle disc as drawn (ah_shuffle*.png), centred in its AH_SHUF_W x AH_BTN_H touch rectangle */
#define AH_PLAY_X 96            /* AH_SHUF_X + (AH_SHUF_W + AH_DISC) / 2 + 12 (the drawn gap): the pill's touch rectangle starts where it is drawn (a playlist's page uses AH_SHUF_X / AH_PLAY_X too) */
#define AH_PLAY_W 180
#define AH_PILL_H 40            /* the pill as drawn (ah_pill*.png), centred in its AH_BTN_H touch rectangle */
/* The pill's glyph and text: the AH_PILL_GLYPH px glyph, AH_PILL_GAP px, then the measured text, centred as a pair in the pill. */
#define AH_PILL_GLYPH 16
#define AH_PILL_GAP 8
/* The header ends 12 px under the Play pill (drawn y 294..334, the touch rectangle AH_BTN_Y 292 + 44 is 2 px taller): the first track row
 * starts there. A playlist's and the Daily Mix page keep the same 12 px gap under their pills. */
#define AH_HDR_H 346
/* Now Playing opens like a track tap (pod_open_player, patch/songops.c): the widget name field the stock pop loop compares
 * (@0x525920 lw a0, 0x10(top)), and at most POP_MAX pages popped. */
#define WIDGET_NAME 0x10
#define WIDGET_STYLE 0x1c /* the style name the widget uses (a char *; show_player_face 0x53bbf0.. compares it with btn_imgfav_style / btn_imgunfav_style before widget_use_style) */
#define POP_MAX 16
/* The cover tint (the album page, the Podcasts Show level; tools/mod_icons.py ah_tint): the window colour is the cover's tone (m1_tone,
 * the constants of Now Playing's) under a black gradient image, ah_tint.png (a window sized child of the page window, first,
 * insensitive), whose alpha runs from AH_TINT_A_TOP on window row 0 to AH_TINT_A_BOT on row AH_TINT_ROWS - 1 (the end of
 * the header: AH_HDR_H) and stays there below (200: the deep tint, 78 % dark), so the transparent track rows and the scroll bar
 * strip show a deep version of the cover colour. AH_WIN_H: the window's height. */
#define AH_WIN_H 450
#define AH_TINT_A_TOP 64
#define AH_TINT_A_BOT 200
#define AH_TINT_ROWS 346        /* AH_HDR_H: the ramp ends with the header */
/* The tone cache (patch/common.c): entries of {key, tone, stamp}, 12 bytes each. The album page names its album as the stock
 * header does: classinfo + 0xd the title, the artist at +0x10d (+0x20d when g_class_type is 0xff14, @0x524b00). */
#define TONE_CACHE_N 64
#define CLASSINFO_ALBUM 0xd
#define CLASSINFO_ARTIST 0x10d
#define CLASSINFO_ARTIST_14 0x20d
#define CLASS_14 0xff14
/* Our album page (patch/albumpage.c, docs/modules/album-page.md; ui/m1plus_album.bin, tools/pod_ui.py build_album_page, which reads this file and must equal it): the
 * header numbers (AH_*: the cover at (AH_ART_X, AH_ART_Y) with AH_CORNER px corners, the lines at AH_TITLE_Y / AH_ARTIST_Y / AH_META_Y, the Shuffle disc and the Play pill at
 * AH_BTN_Y, the rows from AH_HDR_H) in a list that is the whole window (AH_WIN_H, the glass controls float over it). A row is LIST_ROW_H high: the track's number (right aligned in
 * ROW_NUM_W, ROW_NUM_W3 from 100) from x AB_NUM_X, the title AB_NUM_GAP after it to AB_TEXT_END, both in a AB_TEXT_H high line AB_TEXT_Y down the row; the press fill and the 1 px
 * hairline are translucent white over the tint (AB_PRESS, AB_HAIR) across AB_ROW_W (the list less its scroll bar). The select mode's glass buttons (the all / none toggle at
 * AB_SELALL_X, AB_SELALL_W wide; Add, Delete, Cancel AB_BTN_W wide) take the places the stock builder gave them. The Play pill's text label is AB_TEXT_SLACK wider than its text.
 * AB_COVER_MS: the poll of the cache worker that makes a missing cover. AB_ASSET: the window resource. */
#define AB_ASSET "m1plus_album"
#define AB_WINDOW "m1plus_album_page" /* the root widget's name (tools/pod_pages.py ALBUM_PAGE): what navigator_close and the window manager know it by */
#define AB_VIEW_W 320
#define AB_ROW_W 310
#define AB_NUM_X 12
#define AB_NUM_GAP 8
#define AB_TEXT_END 298
#define AB_TEXT_Y 20
#define AB_TEXT_H 22
#define AB_WAVE 12             /* the playing track's marker (ah_wave): a square bitmap right-aligned in the number column */
#define AB_WAVE_Y 24           /* its top in the row: 1 px above the centre of the title's line (AB_TEXT_Y + (AB_TEXT_H - AB_WAVE) / 2 = 25), on the centre of the capitals and digits */
#define AB_WAVE_COLOR 0x00ECEEEEu /* its colour #EEEEEC as a RGBA8888 word (red in the low byte), the rows' wave */
#define AB_PRESS 0x33ffffffu
#define AB_HAIR 0x22ffffffu
#define AB_SELALL_X 0
#define AB_SELALL_W 50
#define AB_ADD_X 116
#define AB_DEL_X 191
#define AB_CANCEL_X 268
#define AB_BTN_W 60
#define AB_TEXT_SLACK 4
#define AB_PLAY_TEXT_W 32      /* the English "Play" at 18 px: where the payload cannot measure the translated text, the pill's pair is centred for this width */
#define AB_COVER_MS 200
#define AB_FOOT_GAP 14         /* the footer ("13 tracks, 49 minutes", ab_foot) starts this far under the last row, at the number column's left edge AB_NUM_X */
#define AB_FOOT_TEXT_H 20      /* its label's height; AB_FOOT_PX 15 grey #AAAAAA */
#define AB_FOOT_PAD 18         /* the content ends this far under the line (14 + 20 + 18 = 52, the Songs page's count has the same) */
#define AB_FOOT_R 10           /* the right margin */
#define AB_FOOT_PX 15
#define REC_CUE_END 0x4c       /* the CUE track's end (loadSongList's twin of REC_CUE_START); the stock row shows a CUE track by its file name when either is set (@0x524c98) */
/* Our Queue page (patch/queuepage.c, docs/modules/queue.md; ui/m1plus_queue.bin, tools/pod_ui.py build_queue_page, which reads this file and must equal it), in place of the stock
 * queue drawer. Window rows (the list is the whole window, QP_WIN_H, the glass Back floats over it): the playing track's QP_COVER px cover (QP_COVER_R corners cut in
 * the alpha) at (QP_COVER_X, QP_COVER_Y) with its title and artist from QP_TEXT_X, QP_TEXT_W wide (QP_TITLE_Y / QP_ARTIST_Y); the Shuffle and Repeat buttons (icon only, QP_PILL_W x SG_PILL_H
 * flat, at QP_PILL_X0 / QP_PILL_X1, y QP_PILL_Y); the "Queue" line at QP_HEAD_Y (QP_HEAD_H high, x SG_HDR_X); then the rows from QP_TOP (the tracks after the playing one, or the grey "No upcoming
 * songs" line QP_EMPTY_Y down from it): LIST_ROW_H high as the Songs page's (the LIST_ART px cover, title and artist from LIST_TEXT_X to QP_TEXT_END, the hairline under the text). A mode
 * button that is on is the light QP_PILL_ON (pressed QP_PILL_ON_DOWN) with the dark glyph (sg_*_on images), off the dark QP_PILL_OFF (pressed QP_PILL_OFF_DOWN) with the white one. QP_TICK_MS: the page's refresh timer (the track and the mode change under it). */
#define QP_ASSET "m1plus_queue"
#define QP_WINDOW "m1plus_queue_page" /* the root widget's name (tools/pod_pages.py QUEUE_PAGE) */
#define QP_WIN_H 450
#define QP_VIEW_W 320
#define QP_COVER 64
#define QP_COVER_X 10
#define QP_COVER_Y 56
#define QP_COVER_R 8
#define QP_TEXT_X 86
#define QP_TEXT_W 224
#define QP_TITLE_Y 65
#define QP_TITLE_H 24
#define QP_ARTIST_Y 91
#define QP_ARTIST_H 20
#define QP_PILL_Y 136
#define QP_PILL_W 145
#define QP_PILL_X0 10
#define QP_PILL_X1 165
#define QP_HEAD_Y 192
#define QP_HEAD_H 28
#define QP_CLEAR_X 210 /* the Clear button right of the "Queue" line: text right-aligned to x 310, 40 px high, centred on the line */
#define QP_CLEAR_Y 186
#define QP_CLEAR_W 100
#define QP_CLEAR_H 40
#define QP_EMPTY_Y 8
#define QP_EMPTY_H 28
#define QP_TOP 226
#define QP_BOTTOM 24
#define QP_TEXT_END 298
#define QP_ROW_W 310
#define QP_TICK_MS 500
#define QP_PILL_ON 0xffc8c8c8u /* #C8C8C8 with the dark glyph (Apple's lit button) */
#define QP_PILL_ON_DOWN 0xffa8a8a8u
#define QP_PILL_OFF 0xff2e2c2cu /* #2C2C2E with the white glyph */
#define QP_PILL_OFF_DOWN 0xff3d3a3au /* #3A3A3D: ROLE_PRESS_QPILL (one blue level off #3A3A3C), so the accent can find it */
#define QP_STREAM_A 2 /* mclGetPlayType values of a stream: the stock queue drawer refuses a row while offline (@0x47a014), our page is for local playback only */
#define QP_STREAM_B 3
#define QP_STREAM_C 0xf0
#define QP_STREAM_D 0xf1

/* ---------------------------------------------------------------------------
 * The Albums grid (patch/albums.c, docs/ui.md). GRID_COLS columns of GRID_COVER px square covers with GRID_GAP px
 * between them, centred (GRID_MARGIN each side: (320 - 2 * 144 - 8) / 2 = 12); under each cover the album
 * (GRID_TITLE_H high, GRID_TITLE_GAP below the cover) and the artist (GRID_SUB_H high), each one line; rows
 * GRID_ROW_GAP apart; the first row GRID_ROW_GAP below the top and the last GRID_ROW_GAP above the bottom. The
 * view is the 400 px under the 50 px navbar (ui/m1plus_albums.bin, tools/pod_ui.py). GRID_TILES covers stay decoded
 * (memory: GRID_TILES * GRID_COVER^2 * 4 = 0.99 MB at most, plus the placeholder).
 * ALBUMS_DEFAULT_GRID is the mode a first use opens (1 grid, 0 list); the choice is then the setting file
 * ALBUMS_FILE. The navbar toggle button is NAV_VIEW_W wide. On the Pod pages (Albums, Artists, Cover Flow's
 * landscape switch; ui assets) it sits at NAV_VIEW_X, flush left of Now Playing (x 260); the page title ends at
 * its left edge.
 *
 * The list mode of the same page: rows LIST_ROW_H high like the library rows (rows.json PITCH 64), a LIST_ART px
 * cover at (LIST_ART_X, LIST_ART_Y), the title (LIST_TITLE_H high at LIST_TITLE_Y, the page's label_row_title
 * style: 21 px white) and the artist (LIST_SUB_H high at LIST_SUB_Y, label_row_sub: 18 px #AAAAAA) from
 * LIST_TEXT_X for LIST_TEXT_W px (12 px right margin); a pressed row is filled LIST_PRESS over its LIST_ROW_H - 1
 * top lines, the last line is the LIST_HAIR hairline. Colours are r,g,b,a bytes of canvas_set_fill_color's word.
 */
#define ALBUMS_DEFAULT_GRID 1
#define GRID_COLS 2
#define GRID_COVER 144
#define GRID_GAP 8              /* between columns */
#define GRID_ROW_GAP 10         /* between rows, and above the first / below the last: two rows (10 + 190 + 10 + 190) fill the 400 px view exactly */
#define GRID_MARGIN 12
#define GRID_R 8                /* the covers' corner radius (the Albums grid and the Recently Played shelf), blended into the black behind them (patch/grid.c) */
#define GRID_TITLE_GAP 4
#define GRID_TITLE_H 22         /* the album, the grid title style (18 px white) */
#define GRID_SUB_H 20           /* the artist, directly under it (15 px #AAAAAA) */
#define GRID_VIEW_H 400
#define GRID_TILES 12           /* the ring: the cells in view, the next rows in the scroll direction, a little history behind */
#define NAV_H 50
#define NAV_VIEW_X 214
#define NAV_VIEW_W 46
#define NAV_CF_X 168            /* the Albums page's Cover Flow button, flush left of the toggle; its title ends here */
#define NAV_CF_W 46
#define LIST_ROW_H 64
#define LIST_ART 52
#define LIST_R 4                /* the list covers' corner radius: cut in the bitmap's alpha (a pressed row's fill shows behind them; patch/grid.c blend) */
#define LIST_ART_X 10
#define LIST_ART_Y 6            /* centred above the row's 1 px hairline: 6 px over the cover, 5 under it */
#define LIST_TEXT_X 74          /* LIST_ART_X + LIST_ART + 12 */
#define LIST_TEXT_W 234         /* to the 12 px right margin: 74 + 234 + 12 = 320 */
#define LIST_HAIR_END 310       /* the hairline of a list row runs from its text to here (Search's rows': 68..310), the Apple inset */
#define LIST_CHEV_X 288         /* a row that opens a page: the shared chevron (m1_make_chevron, POD_CHEV_W x POD_CHEV_H) from this x (Search's SE_CHEV_X), on the row's middle above the hairline */
#define LIST_TEXT_W_CHEV 204    /* the text of such a row ends at 278 (Search's SE_END_CHEV): 74 + 204 */
#define LIST_TITLE_Y 9
#define LIST_TITLE_H 24
#define LIST_SUB_Y 35
#define LIST_SUB_H 20
#define LIST_HAIR 0xff222222u
#define LIST_PRESS 0xff343333u /* ROLE_PRESS_ROW #333334 as a color_t word: a pressed row, unique so the accent can find it */

/* ---------------------------------------------------------------------------
 * Now Playing (patch/nowplaying.c, docs/architecture.md section 8a, ui assets tools/mod_nowplaying.py). The hook is
 * on playing_page_init (0x53d1e4). Timer callbacks answer RET_REPEAT to run again (the stock page timer does:
 * player_timer_start @0x53c210 registers 0x53cf48, which returns 8 while the page lives) and RET_OK to end.
 * COVER_SRC is the cover source type word (0x97cad8): parseplaycover_thd (0x4ded84) sets it to 1 before it
 * replaces the files and to 2 (/tmp/coverpic.jpg, embedded art), 3 (/tmp/externpic.jpg, a folder image) or 5
 * (/tmp/externpic.jpg, copied from the .downpic cache) once the file is complete; the page's cover loader
 * (0x53a5d8) reads exactly these. Any other value has no JPEG file (4 random_cover, 6/7 streamed).
 * NP_NEUTRAL is the no-cover tone; the cover's tone has value NP_V_MIN..NP_V_MAX and keeps NP_SAT_NUM/NP_SAT_DEN of
 * the colour's distance from its brightest channel, so the 0.15..0.92 black gradient over it leaves the white title and the #AAAAAA lines at least 4.5:1 (test/pod/nowplaying.py).
 */
#define RET_REPEAT 8
#define COVER_SRC_BUSY 1
#define COVER_SRC_EMBEDDED 2
#define COVER_SRC_FOLDER 3
#define COVER_SRC_CACHE 5
#define NP_TICK_MS 500
#define NP_HASH_MAX 524288
#define NP_KEY_NEUTRAL 1
#define NP_KEY_TONE 2
#define NP_NEUTRAL 0xff202020u
#define NP_V_MIN 32
#define NP_V_MAX 192
#define NP_SAT_NUM 23
#define NP_SAT_DEN 25
/* The cover's rounded corners (painted by the payload, np_on_art_paint) and the gradient under them (np_tint.png:
 * black, alpha NP_ALPHA_TOP on the window's first row to NP_ALPHA_BOTTOM on its last, NP_WIN_H rows): the cover is
 * NP_ART px square at window y NP_ART_Y, its corners NP_ART_R px. Equal to the constants of tools/mod_nowplaying.py. */
#define NP_ART 264
#define NP_ART_Y 28
#define NP_ART_R 12
#define NP_ALPHA_TOP 38
#define NP_ALPHA_BOTTOM 235
#define NP_WIN_H 450
/* The info page's lines (np_info): the stock text is read into NP_INFO_BUF bytes (stock writes them with a 0x200
 * buffer, so a longer text is never rewritten); the quality line keeps single spaces round its bars when the result is
 * at most NP_INFO_SPACED characters (the label is 304 px wide at 18 px, 8 px from each side: such a line is at most 272 px
 * wide, a DSD line without the spaces at most 295). */
#define NP_INFO_N 6
#define NP_INFO_BUF 512
#define NP_INFO_SPACED 36
/* The status bar follows the page (EXPERIMENTAL, np_bar_*): the window events of the page (widget_on on the window:
 * window_manager_default_open_window dispatches 0x12c to the window a new non-keyboard, non-overlay window covers and 0x12d
 * to the one it uncovers, @0x69182c / @0x691b3c), the stock black, and the largest weighted square sum (2126 r^2 + 7152 g^2
 * + 722 b^2, channels 0..255) the bar colour may have: gamma 2 is above the sRGB luminance, so L <= 0.183 and white text
 * keeps 4.5:1 (test/pod/nowplaying.py checks the true figure). */
/* (EVT_WINDOW_WILL_OPEN: see WINDOW_STAGE_CREATED; a handler bound on the window runs after stock has resolved the styles, widget_dispatch calls the widget's
 * on_event @0x66cf38 before the emitter @0x66cf6c) */
#define EVT_WINDOW_WILL_OPEN 0x12a
#define EVT_WINDOW_TO_BG 0x12c
#define EVT_WINDOW_TO_FG 0x12d
#define NP_BAR_STOCK 0xff000000u
#define NP_BAR_LUM_MAX 119000000u
/* The lyrics page (patch/lyrics.c, docs/modules/lyrics.md). The view np_lyrics is LY_W x LY_VIEW_H (tools/mod_nowplaying.py LYR_*: the stock list's rectangle);
 * the current line's top is LY_ANCHOR (0.35 of the view) down it. The text is LY_FONT px, left aligned, in a label LY_W wide (the page's 28 px margin each side). A text row is LY_LINE_H px (the font plus the style's `spacer`, tools/mod_nowplaying.py LYR_SPACER: AWTK's own row pitch inside a wrapped label), a line has 1..LY_LINES_MAX of them (a wrapped line) and LY_GAP below. A line of only Latin, Greek and Cyrillic takes the bold face (font file lyrics.ttf), any other line the default font (AWTK has no per-glyph fallback).
 * The labels are a pool of LY_POOL (slot = line % LY_POOL; a view touches at most 6 lines of the smallest pitch, 9 with the one above and below). Lines are read from the stock rows
 * (at most LY_MAX; each row's int property "lrc_time" and its text, LY_BUF bytes). A move of the anchored line is a damped spring of LY_SPRING_MS per line (a table of 65 entries, overshoot cut at LY_OVERSHOOT_MAX px), each line starting LY_DELAY_MS
 * (shrinking 20/21 a line) after the one before, in LY_FRAME_MS steps; a move over LY_SNAP_LINES lines jumps. The window of lines laid out round the anchor is LY_POOL, those
 * further than LY_OFF_MAX px are not measured (4 x LY_VIEW_H, the most an offset can be, ly_move: a move of LY_SNAP_LINES lines of LY_LINES_MAX rows is 929 px, and a line that was on the screen has to stay laid out until its spring has taken it out). Touch: a vertical drag over LY_TAP_PX scrolls, LY_IDLE_MS after the last touch the lines come back, a tap under LY_TAP_PX (not within
 * LY_COAST_MS of a started move) seeks (seek_time) and the tick leaves the lines alone for LY_HOLD_MS. Opacity table 1.0 / 0.45 / 0.32 / 0.24 / 0.18, times an edge factor over the last LY_FADE px at the top and bottom of the view. LY_FIT_W (LY_W less the style's 2 px margins each side) is what a one-row line may measure, LY_ROW_W (one less: stock's wrap check adds 1 px) what a row of a broken line may (ly_break). A line past LY_LINES_MAX rows is cut and ends in LY_MARK (U+2026). An anchored line of more than three rows sits higher (ly_anchor): the next line's first row ends LY_ANCHOR_ROOM px above the view's bottom, the line's top not above LY_ANCHOR_MIN. get_playtime is the stock call the lyric timers compare "lrc_time" with (0x5385e0). */
#define LY_W 264
#define LY_VIEW_H 244
#define LY_ANCHOR 85
#define LY_FONT 30
#define LY_LINE_H 34
#define LY_GAP 12
#define LY_FADE 56
#define LY_BROWSE_OP 153
#define LY_LINES_MAX 6
#define LY_ANCHOR_MIN 20
#define LY_ANCHOR_ROOM 8
#define LY_MARK "\xe2\x80\xa6"
#define LY_POOL 20
#define LY_MAX 400
#define LY_BUF 256
#define LY_FRAME_MS 40
#define LY_SPRING_MS 640
#define LY_OVERSHOOT_MAX 6
#define LY_DELAY_MS 50
#define LY_SNAP_LINES 4
#define LY_OFF_MAX 976
#define LY_IDLE_MS 3000
#define LY_TAP_PX 10
#define LY_COAST_MS 200
#define LY_HOLD_MS 1000
#define LY_FIT_W 260
#define LY_ROW_W 259
#define LY_MISS_MAX 20
/* The window "stage" from which a widget's style can be resolved: window_base_on_event's EVT_WINDOW_WILL_OPEN (0x12a) stores 2 (@0x676bb8, @0x676bc8), loads the
 * window's own theme (styles/playing_page.bin, where np_lyric_style lives) and resolves every widget's style (widget_update_style_recursive @0x676bd4). Stock
 * dispatches that event from an idle, so after playing_page_init (our np_start) has returned. widget_use_style resolves the new style only in an opened window
 * (stage 3 or 5, @0x66aac0); before that and during the open animation it only marks the widget, and widget_measure_text measures in the old style. */
#define WINDOW_STAGE_CREATED 2
/* The interlude dots (docs/modules/lyrics.md, stage 4): LY_DOT px white circles (the image np_dot), LY_DOT_PITCH apart from x LY_DOT_X, centred on the anchor row (LY_DOT_PAD = LY_LINE_H + LY_GAP: the lines sit
 * that far below while they show) for a gap before the first line of at least LY_DOT_MIN_S seconds. Dot k fills from LY_DOT_DIM (0.25) to 255 as the k-th third of the gap (less its last fade) passes, the group breathes
 * between 255 and LY_DOT_BREATH_MIN every LY_DOT_BREATH_MS, and fades out over the last LY_DOT_FADE_MS. One LY_DOT_MS timer exists while they show and the player plays. */
#define LY_DOT 10
#define LY_DOT_PITCH 18
#define LY_DOT_X 2
#define LY_DOT_PAD 46
#define LY_DOT_MIN_S 4
#define LY_DOT_MS 80
#define LY_DOT_DIM 64
#define LY_DOT_FADE_MS 500
#define LY_DOT_BREATH_MS 2400
#define LY_DOT_BREATH_MIN 160

/* ---------------------------------------------------------------------------
 * The mini player bar on the Home instance of the menu (patch/minibar.c, docs/modules/minibar.md; the widgets are in
 * ui/m1plus_menu.bin, tools/pod_ui.py MB_*, which must equal these). Apple Music's floating mini player: a full pill in the 450 px
 * window, MB_W x MB_H at (MB_X, MB_Y), corner radius MB_R = MB_H / 2, a pre-rendered translucent glass image (mb_glass, mb_glass_down:
 * dark fill, sheen, rim light; the card button's bg_image; not tinted by the album). The cover is MB_ART px square, MB_ART_X from the pill's left and MB_ART_Y from its top, its
 * four corners MB_ART_R px (alpha in the bitmap). Title (17 px white) and artist (16 px, light grey) are hscroll_labels MB_TEXT_W wide
 * from MB_TEXT_X (ellipsis, never scrolling); play (or pause, one of the two shows) and next are MB_BTN_W x MB_H touch targets at
 * MB_PLAY_X / MB_NEXT_X (glyph centres 51 px apart, the next centre 35 px from the pill's right end). The list always runs to the window
 * bottom, under the translucent pill; while the bar shows, a trailing spacer row pod_pad (MB_PAD high) is visible so the last row can scroll
 * clear above it (the stock list_view layout keeps it: it sums every visible child's own height). MB_FIRST_MS: the one-shot that starts the page timer (nothing runs
 * in the menu's first paint), MB_TICK_MS its period; MB_SETTLE: ticks that re-read the /tmp cover file after a track change (demo
 * writes it a little later). MB_PLAYING: mclGetPlayStatus() while playing.
 */
#define MB_X 8
#define MB_Y 384
#define MB_W 304
#define MB_H 56
#define MB_R 28
#define MB_GAP 8
#define MB_PAD 64          /* the list's bottom padding while the bar shows: a trailing spacer row pod_pad of this height, so the last row scrolls clear above the pill (WIN_H - HOME_PAD - (MB_Y - MB_GAP)) */
#define MB_ART 36
#define MB_ART_X 14
#define MB_ART_Y 10
#define MB_ART_R 5
#define MB_TEXT_X 60
#define MB_TEXT_W 130
#define MB_TITLE_Y 7
#define MB_TITLE_H 22
#define MB_ARTIST_Y 29
#define MB_ARTIST_H 20
#define MB_PLAY_X 194
#define MB_NEXT_X 245
#define MB_BTN_W 48
/* The lock screen's mini player layout (patch/lockscreen.c, tools/mod_lockscreen.py MINI, docs/modules/lockscreen.md): the stock card re-laid as the Home bar's numbers
 * above (MB_W x MB_H card with the mb_glass image, the MB_ART cover at MB_ART_X / MB_ART_Y, title and artist at MB_TEXT_X, play and next at MB_PLAY_X / MB_NEXT_X), at
 * LK_MINI_X / LK_MINI_Y in the 320 x 480 window (10 px over the swipe hint); title and artist LK_TITLE_PX / LK_ARTIST_PX px, the artist colour LK_ARTIST_RGB. */
#define LK_MINI_X 8
#define LK_MINI_Y 386
#define LK_TITLE_PX 17
#define LK_ARTIST_PX 16
#define LK_ARTIST_RGB "#D0D0D0"
#define LK_DATE_NAME "dclock_date" /* the lock screen's date (a digit_clock; patch/lockscreen.c lk_date) */
#define MB_FIRST_MS 120
#define MB_TICK_MS 500
#define MB_SETTLE 3
#define MB_PLAYING 2
#define MB_GREY 0xff2b2b2bu
/* The backdrop blur behind the glass (EXPERIMENTAL, patch/minibar.c mb_blur, tools/pod_blur.py, docs/modules/minibar.md): the pixels under the pill are
 * read from and written to the lcd's drawing buffer in the card's EVT_BEFORE_PAINT, only when every pin below holds at run time.
 * EVT_BEFORE_PAINT: widget_paint dispatches 0x11f right after canvas_translate to the widget and before widget_on_paint_background (@0x66dd98), 0x120 after
 * the children and the border (@0x66de3c). canvas_t: ox, oy at 0 / 4 (canvas_translate @0x6434d4 adds to them), the clip rectangle left, top, right, bottom
 * (inclusive) at 0x10..0x1c (canvas_get_clip_rect @0x643718 turns it into x, y, w, h), its lcd at 0x30 (canvas_get_width @0x64352c passes it to lcd_get_width).
 * lcd_t: the first word is begin_frame (lcd_begin_frame @0x657b60 `lw v0, (a0)`, @0x657b8c `lw t9, (s0); jr t9`); the 565 memory lcd's init @0x695dc8
 * (reached by lcd_mem_bgr565_init @0x696bc4, bitmap_get_bpp_of_format(6) = 2 bytes @0x695e20) stores 0x695cb0 there (@0x695ec4), width and height at
 * 0xb0 / 0xb4 (@0x695eb0, @0x695eb8; lcd_get_width @0x658484 reads 0xb0), line length at 0x120 (and 0x124: its set_line_length @0x695034 writes both; init @0x695ed0 =
 * width x 2), and the drawing buffer at 0x110 (lcd_mem_set_fb @0x695d9c `sw a1, 0x110(a0)`; the double-buffered create @0x696cc4 stores the online one at 0x114
 * and gives the offline one to that setter). Any other lcd type (the 5551 special one, 24/32 bit) fails the begin_frame word and gets no blur.
 * MB_HW x MB_HH: the half-resolution plane (4 bytes a block, calloc'd once). MB_BLUR_OFF: an SD file that turns the blur off. */
/* EVT_SCROLL 0x152: the scroll_view's yoffset setter (0x60ff08) builds offset_change_event_init(e, 0x152, widget, new, old) and widget_dispatch es it to the scroll view
 * (@0x60ff38..0x60ff74); it is called by scroll_view_scroll_delta_to (the drag, @0x610b9c), scroll_view_set_offset (the fling and scroll_to animations, @0x6116b4)
 * and the property setter (@0x611dfc), every way the list's offset changes. The list scrolls under the pill, so the pill is invalidated on it (mb_on_scroll). */
#define EVT_SCROLL 0x152
#define EVT_BEFORE_PAINT 0x11f
#define CANVAS_OX 0x00
#define CANVAS_OY 0x04
#define CANVAS_CLIP 0x10
#define CANVAS_LCD 0x30
#define LCD_BEGIN 0x00
#define LCD_W 0xb0
#define LCD_H 0xb4
#define LCD_FB 0x110
#define LCD_LINE 0x120
#define LCD_565_BEGIN 0x695cb0u
#define MB_HW 152          /* MB_W / 2 */
#define MB_HH 28           /* MB_H / 2 */

/* ---------------------------------------------------------------------------
 * The Recently Played shelf on the Home instance of the menu (patch/recent.c, docs/modules/recent.md; the widgets are in
 * ui/m1plus_menu.bin, tools/pod_ui.py SH_*, which reads GRID_* from this file and must equal the rest). The shelf is the Albums grid
 * (patch/grid.c, the GRID_* geometry above: GRID_COVER covers, GRID_GAP apart, from x GRID_MARGIN, the album GRID_TITLE_H and the artist
 * GRID_SUB_H under each, rows GRID_ROW_GAP apart) in a view of its own, SH_W (the scroll view's width) wide: a child of pod_scrollview that
 * follows the last shown row (Settings), before the mini bar's spacer, hidden and insensitive in the asset, scrolling with the list.
 * GRID_COLS x SH_ROWS cells, the SH_TILES (= RC_MAX) most recent albums, row-major; ceil(albums / GRID_COLS) rows, SH_H(n) high, SH_HMAX at most: the
 * payload sets the view's height before the rows are arranged and the menu sums it into virtual_h. The 2 cells of a row end at
 * GRID_MARGIN + 2 * GRID_COVER + GRID_GAP = 308, inside the 310 px scroll view. At the top a section header, the stock hscroll_label
 * pod_sh_head (the translation of \"Recently Played\", SH_HEAD_PX white, one line cut with an ellipsis, insensitive) at x SH_HEAD_X,
 * SH_HEAD_TOP from the top, SH_HEAD_W x SH_HEAD_H (its text starts 2 px in: the label's margin, so it lines up with the covers at
 * GRID_MARGIN), then SH_HEAD_GAP of air; its ink starts 20 px below the Settings row and ends 8 px above the covers (the line box has a
 * little slack). The first row starts at SH_TOP = SH_HEAD_TOP + SH_HEAD_H + SH_HEAD_GAP; nothing below the last artist line (SH_BOTTOM), so
 * scrolled to the end it is MB_GAP above the pill. The covers' corners are the Albums grid's (GRID_R).
 * RC_MAX: entries the file keeps; RC_FIRST_MS: the one-shot that starts the page timer (the menu's first paint decodes nothing);
 * RC_TICK_MS: one cover decoded per tick; RC_TAP_PX: a release closer than this to the press (both axes) is a tap (the scroll view's own
 * drag threshold, SC_DRAG_PX: from there on it drags). The file: RC_MAGIC line, then one line per album (tools/pod_recent.py)
 * (the most recent first); RC_STR / RC_PATH: bytes kept per name / path (NUL included); RC_FILE_MAX: the most bytes read.
 */
#define SH_W 310
#define SH_ROWS 3
#define SH_TILES 6          /* GRID_COLS * SH_ROWS, and RC_MAX: every album the file keeps (patch/recent.c #errors if they differ) */
#define SH_HEAD_X 10
#define SH_HEAD_W 300
#define SH_HEAD_TOP 17
#define SH_HEAD_H 22
#define SH_HEAD_PX 20
#define SH_HEAD_GAP 5
#define SH_TOP 44
#define SH_BOTTOM 0
#define SH_H(n) (SH_TOP + (n) * GRID_CELL_H + ((n) - 1) * GRID_ROW_GAP + SH_BOTTOM)   /* the shelf's height for n rows of covers: 234, 434, 634 */
#define SH_HMAX SH_H(SH_ROWS)
#define RC_MAX 6
#define RC_STR 96
#define RC_PATH 256
#define RC_FILE_MAX 3072
#define RC_FIRST_MS 150
#define RC_TICK_MS 30
#define RC_TAP_PX 10
#define RC_RESOLVE_MS 5000   /* the menu's to-foreground resolves an album's cover key (loads the stock album list) only this long after the menu opened */


/* ---------------------------------------------------------------------------
 * List gestures (patch/scroll.c, docs/architecture.md "List gestures"). The stock scroll_view (g_scroll_view_vtable
 * 0x97a298; every stock list is list_view > scroll_view > list_item rows) keeps its drag state in the widget:
 * scroll_view_t fields as its on_event (0x610724) and scroll_view_is_dragged (0x61064c) read them. The hook is the
 * vtable's on_event_before_children slot, which widget_on_event_before_children (0x666c34) calls with every pointer event
 * before the widget's children see it. widget_animator_t: manager @0x58, state @0x28 (1 = running, widget_animator_start
 * @0x673114), the widget it animates @4.
 */
#define SC_RET_STOP 0xb         /* ret_t RET_STOP: widget_on_pointer_down returns at once, children and the widget itself skipped (@0x671324) */
#define SC_XSLIDE 0x90          /* scroll_view_t: xslidable, yslidable, snap_to_page (bytes; is_dragged @0x610680, @0x610688, @0x6106cc) */
#define SC_YSLIDE 0x91
#define SC_SNAP 0x92
#define SC_DOWN_X 0x98          /* the pointer-down position (on_event DOWN stores e->x, e->y @0x61086c, @0x61087c) */
#define SC_DOWN_Y 0x9c
#define SC_PRESSED 0xa0         /* bytes: pressed (set by DOWN, @0x61083c) and dragged (set by the first MOVE past the threshold, @0x610c34) */
#define SC_DRAGGED 0xa1
#define SC_WA 0xe8              /* the running scroll animator (scroll_view_scroll_to @0x610548); cleared by the end handler 0x6101b8 (@0x610208) */
#define SC_AN_STATE 0x28        /* widget_animator_t: state, 1 = running (widget_animator_start @0x673114) */
#define SC_AN_WIDGET 0x04       /* the widget it animates (widget_animator_stop reads it @0x673258) */
#define SC_AN_RUNNING 1
#define SC_DRAG_PX 10           /* scroll_view_is_dragged's threshold: slti .., 0xa @0x6106e0 (kept) */
#define SC_YOFF 0x84            /* scroll_view_t yoffset (int): the setter 0x60ff08 stores it `sw s1, 0x84(s0)` @0x60ff78, the list_view layouter clamps it @0x60b250..0x60b278 (xoffset 0x80, virtual_h 0x7c) */
#define EVT_SCROLL_END 0x151    /* widget_dispatch_simple_event(scroll_view, 0x151), the last thing the scroll animation's end handler 0x6101b8 does (@0x610238..0x610248; 0x14f before it) */

/* libc constants (MIPS Linux) the payload passes to the stock libc stubs */
#define F_OK 0
#define O_RDONLY 0
#define O_WRONLY 1
#define O_RDWR 2
#define O_APPEND 0x8
#define O_CREAT 0x100
#define O_TRUNC 0x200
#define PROT_READ 1
#define MAP_SHARED 1
#define MAP_FAILED ((void *)-1)

/* Now Playing's More dialog (patch/playmore.c, docs/modules/playmore.md): ui/dialog/playmore_dialog.bin is a 320 px wide
 * sheet pinned at y 130 (the stock init, @0x479d10, and its to-background handler @0x4789f0) holding list_view playmore_listview >
 * scroll_view playmore_scrollview (310 px, the scroll bar scroll_bar_m beside it, 10 px) > list_item rows, PM_ROW_H (50, the
 * list_view's item_height) high each; the asset adds the hidden rows pod_more, pod_back, pod_tape, pod_vinyl, pod_goep, pod_art and pod_sleep. The payload shows PM_PAGE_N rows (page 1) or PM_PAGE2_N
 * (page 2) at a time and puts the sheet, as high as they are, on the bottom of the 480 px screen (the stock 130 + 350 ends there too). */
#define PM_ROW_H 50
#define PM_PAGE_N 6               /* page 1's rows (Look up album, Look up artist, Add to playlist, Cassette Mode, Vinyl Mode, More; the asset's pod_goep, Go to Podcasts, is the episode's first row): the sheet is that high (PM_ROW_H x) */
#define PM_PAGE_EP_N 2            /* page 1 of a podcast episode (Go to Podcasts, More) */
#define PM_PAGE2_N 6              /* page 2's rows (the back header, Speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete) */
#define PM_SCREEN_H 480
#define PM_DIALOG_W 320
#define PM_SV_W 310
#define PM_BAR_W 10

/* The Playlists page (patch/playlists.c, docs/modules/playlists.md). Playlists live in /mnt/data/database.db, table `playlist`: a row with
 * id <= 100 is a playlist (getAllPlayList @0x4ec4e8: `select * from playlist where id <= 100`; its name is REC_TITLE, its id REC_ID and also
 * REC_DISC, createPlayListItem @0x4eeca8 stores both), a row with id > 100 is a song (getMusicByPlayList @0x4eddac: `where id > 100 and
 * cd_num=<id>`, no ORDER BY: insertion order) with the same 18 columns as a library song, so its album and artist are as they were when it was
 * added. loadLocalClassList(CLASS_PLAYLISTS) puts the playlists in *pdeq_playlist (@0x4ee614: getAllPlayList, assigned @0x4ee63c), and
 * (CLASS_PLAYLIST_SONGS) the songs of playlist classinfo[1] in *pdeq_showlist (@0x4ee744). The stock Playlists page opens a playlist (the
 * shared row handler @0x53d300, mode 0): the playlist's name into nagvation_title (snprintf "%s", 0x200 @0x53d5b8), its REC_DISC into
 * classinfo[1] (@0x53d5f4), navigator_to_with_context("allmusic_page", 0xff13). PL_MAX: ids 1..100. */
#define CLASS_PLAYLISTS 0xf00b
#define CLASS_PLAYLIST_SONGS 0xff13
#define PL_MAX 100
#define PL_SCAN 50             /* songs read per playlist for the mosaic: the first PL_SCAN, in order */
#define PL_MORE_MS 16
/* The popup cards' shared geometry: the view-sort card (VS_* below) hangs its right edge at PL_CARD_RIGHT, PL_CARD_Y, at most PL_CARD_MAX wide (the widest of the 13 languages fits); PL_MENU_ROWS rows of PL_ROW_H
 * (Now Playing's More sheet's 50 px rows) are the pl_glass card of the two dialogs that borrow it (the Podcasts refresh, the Software Update download popup). The Playlists page's own "..." card is the view-sort card. */
#define PL_MENU_ROWS 4
#define PL_CARD_RIGHT 311      /* flush with the navbar glass's right end */
#define PL_CARD_Y 52           /* 6 px under the glass (y 4 .. 46) */
#define PL_CARD_R 14
#define PL_ROW_H 50
#define PL_CARD_MAX 292
/* The track rows' "..." menu (patch/rowmenu.c, tools/pod_ui.py row_menu, docs/modules/rowmenu.md): each row of the album page and of the Songs page's lists ends with a grey "..." (RM_DOTS_PX px,
 * RM_DOTS_RGB) centred in a RM_MORE_W wide tap zone (flush with its right edge beside the rail) whose right edge is RM_MORE_RIGHT (the list's width); on the Songs page, while the A-Z rail is shown, RM_MORE_RIGHT_RAIL (flush with the rail's
 * touch column, which starts at SG_RAIL_X 284). The row's text ends RM_TEXT_GAP before the zone. A tap on it opens the sheet: RM_ROWS rows of PM_ROW_H at the window's foot in
 * Now Playing's More sheet's glass (pc_sheet5, 320 x 250, top corners only), laid out by the asset (the payload only shows and hides it). */
#define RM_ROWS 5
#define RM_MORE_W 44
#define RM_MORE_RIGHT 310
#define RM_MORE_RIGHT_RAIL 284
#define RM_TEXT_GAP 4
#define RM_DOTS_PX 24
#define RM_DOTS_RGB 0x008c8c8cu
/* The Podcasts refresh dialog (tools/pod_ui.py podcasts_dialog, patch/podcasts.c pg_dlg_*): the Playlists card's glass, PD_CARD_W wide and exactly as high as that image (4 rows of 50),
 * centred in the 450 px client area; the progress bar is PD_BAR_W wide (the fill's width is the payload's) and PD_BAR_H high; the Cancel row fills the card's last PL_ROW_H. */
#define PD_CARD_W 280
#define PD_CARD_H 200
#define PD_BAR_W 240
#define PD_BAR_H 6

/* ---------------------------------------------------------------------------
 * The Songs page (patch/songs.c, docs/modules/songs.md; the widgets are in ui/m1plus_songs.bin, tools/pod_ui.py SG_*, which reads this file and must equal it).
 * The library as one list under the glass navbar: the content view (view_grid, inside the stock list_view > scroll_view, as the Albums page) holds, from its top,
 * the large title (a label, SG_TITLE_PX px, x SG_TITLE_X, SG_TITLE_H high), the Play and Shuffle pills (real flat buttons, SG_PILL_W x SG_PILL_H at x SG_PILL_X0
 * and SG_PILL_X1, y SG_PILL_Y, corner radius SG_PILL_R; the glyph and the label are centred as a pair SG_PILL_GAP apart; a playlist's page has the album page's Shuffle disc and
 * Play pill instead, hd_shuffle / hd_play at AH_SHUF_X / AH_PLAY_X, 44 px high buttons from y PH_BTN_Y whose pictures are drawn centred in them, the glyph an image and the
 * text painted by the page, patch/common.c m1_pill_place) and from y SG_TOP the songs: with the
 * stock Title order (sort_flag 0) in sections, each a SG_HDR_H high header (the letter SG_HDR_PX px white at x SG_HDR_X on the page's black, no band, as the Recently Played
 * shelf's header; only the pinned copy is filled, SG_HDR_BG, so the rows scrolling under it are hidden) and its rows; in any other order the rows only. A row is LIST_ROW_H high as the library rows (the cover LIST_ART at (LIST_ART_X, LIST_ART_Y), the title at
 * LIST_TITLE_Y, the artist at LIST_SUB_Y, from x LIST_TEXT_X to SG_TEXT_END, the hairline from there); in select mode every row's content moves SG_SEL_COL right and
 * a SG_MARK px mark (the stock `selected` / `unselect` images) sits in the column. The pinned header (the section the window's top is in) is painted over the
 * rows and pushed up by the next one. The rail (a widget of its own, x SG_RAIL_X, SG_RAIL_W wide, as high as the drawn span plus SG_RAIL_PAD above and below and centred on the list,
 * outside the scroll_view so a touch on it never starts a drag; letters and dots are aligned from the font's metrics, SG_RAIL_INK2 and SG_RAIL_DX of stock.h): a compact index like the stock Songs page's (its A * . . F . . K image, search_icon.png): items SG_RAIL_PITCH px apart centred on x SG_RAIL_CX and
 * vertically on the list, at most SG_RAIL_ITEMS of them (SG_RAIL_PITCH x SG_RAIL_ITEMS px); the sections' letters, all of them when they fit, else every k-th (the first and
 * last always) with a SG_RAIL_DOT px dot between two letters; a finger's position along the drawn span is mapped to ALL the sections; the touched letter (when it is a drawn
 * one) on a SG_RAIL_DISC px disc (pal_fill(): the accent, Neutral #EEEEEC) with a black letter; a SG_BUBBLE px bubble (a widget) shows the real letter. In select mode a SG_BAR_H high bar at the window's
 * bottom holds the Add to playlist and Delete pills. The navbar's title shows from scroll offset SG_COLLAPSE on (the large title has gone). HOME_MYMUSIC: the stock
 * Songs page's Home id, where a window that will not open falls back. SG_MAX_SEC: room for the sections (one per rank: "#" and A..Z, patch/songs.c SG_RANKS). SG_BUILD_N: the songs either side
 * of the first one in view the background cover build looks at; SG_BUILD_MOVE the distance the page has to scroll before it looks again.
 * The stock multi-select's selection vector is `*0xa045e0` (SEL_VEC in tools/pod.py); the picker the stock Add button opens is playlist_page with the context
 * (1 << 16 | class), where it adds the selection to the row's playlist and closes itself (@0x53d300, mode 1).
 */
#define HOME_MYMUSIC 3
/* The same page lists the other stock song lists (docs/modules/songs.md "The other lists"): the Home tiles the menu rows name (tools/pod_pages.py HOME_*, where a window
 * that will not open falls back) and the loadLocalClassList class of each (docs/modules/addresses.md; CLASS_RECENT, CLASS_OFTEN, CLASS_FAV, CLASS_PLAYLIST_SONGS are
 * defined with their first users). SG_NAME_MAX: the wide chars of a list's title (a playlist's name) the ellipsis fit looks at. */
#define HOME_HIRES 9
#define HOME_FAV 10
#define HOME_MOST 11
#define HOME_RECENT 12
#define HOME_RECENTADD 13
#define CLASS_HIRES 0xf002
#define CLASS_RECENTADD 0xf009
#define SG_NAME_MAX 128
#define REC_TIME_CREATE 0x50  /* stSongInfo: songtable.time_create (column 14), seconds since the epoch: atoi(argv[14]) @0x4e9344 stored at @0x4e9358; the order of Recently Added (docs/modules/recent-albums.md); the album view reads the query in this order and never the field */
#define REC_INITIAL 0x54      /* stSongInfo: the songtable's Initial column (15), a byte: the ASCII code of '*' (a title that starts with a digit), 'A'..'Z' (the first letter, a CJK character as its pinyin initial) or '#' (anything else); written by the scan (@0x5edcb8), read by the row callback (@0x4e936c) and copied by 0x5db54c (@0x5db9ac); 0 = never written */
#define NAV_TITLE_X 58           /* the glass navbars' title (tools/pod_ui.py NAV_TITLE_X) */
#define SG_SELALL_X 208         /* the select mode's Select All text button (to the right edge) */
#define SG_TITLE_X 12
#define SG_TITLE_W 296          /* the large title's width on every page: the screen less its margin on both sides, cut with an ellipsis */
#define SG_TITLE_H 52
#define SG_PILL_Y 52
#define SG_PILL_H 40
#define SG_PILL_W 129
#define SG_PILL_X0 10
#define SG_PILL_X1 149
#define AL_PLAY_X 10             /* an artist's albums page (patch/albums.c): Play x 10 .. 155 and Shuffle x 165 .. 310, both 145 wide with a 10 px gap (the Songs page's select-bar pills' width; the Songs page's own pills keep SG_PILL_W / SG_PILL_X0 / SG_PILL_X1) */
#define AL_PLAY_W 145
#define AL_SHUFFLE_X 165
#define AL_SHUFFLE_W 145
#define AL_PILLS_END 92          /* where that page's pill block ends (SG_PILL_Y + SG_PILL_H): the grid's first gap or the list's first row follows, GRID_ROW_GAP under it */
#define AL_PHOTO_D 88            /* an artist's page with a photo header (patch/albums.c, docs/modules/albums.md): the circle, 88 px, centred, 8 px under the navbar (much smaller than the album page's 160 px cover) */
#define AL_PHOTO_X 116
#define AL_PHOTO_Y 8
#define AL_NAME_Y 110            /* the name's box (PH_NAME_X / _W / _H): 14 px under the circle */
#define AL_HEAD_PILL_Y 148       /* the pills' y, 16 px under the name's box */
#define AL_HEAD_END 188          /* where that block ends (AL_HEAD_PILL_Y + SG_PILL_H): the grid's first gap or the list's first row follows, as AL_PILLS_END */
#define AL_HEAD_COLLAPSE 132     /* the navbar shows the small title once the name's box (its bottom, AL_NAME_Y + PH_NAME_H) has scrolled away */
#define SG_BAR_PILL_W 145       /* the select bar's pills (Add to Playlist needs the room; the bar is below the rail, whose touch column ends at the bar's top) */
#define SG_BAR_PILL_X1 165
#define PL_BAR_PILL_W 300        /* the Playlists page's select bar has the one pill, Delete, across the bar (x SG_PILL_X0, a 10 px margin each side) */
#define SG_PILL_R 20
#define SG_PILL_GLYPH 16
#define SG_PILL_GAP 8
#define SG_PILL_PX_SMALL 16     /* a pill label too wide beside its glyph at 18 px is drawn at this size (patch/common.c m1_centre_pill) */
#define SG_TOP 104
#define SG_HDR_H 28
#define SG_HDR_X 10
#define SG_HDR_BG 0xff000000u
#define SG_SEL_COL 30
#define SG_MARK 26
#define SG_RAIL_X 284        /* the touch column: x 284..320, 36 wide; the drawn letters and dots stay centred on x SG_RAIL_CX */
#define SG_RAIL_W 36
#define SG_RAIL_CX 310
#define SG_RAIL_INSET (LIST_HAIR_END - SG_RAIL_X) /* 26: while the rail is shown the rows give up this much on the right (the rail's touch column starts at SG_RAIL_X, the hairline ends at LIST_HAIR_END): hairline end, chevron x and text end move left by it (patch/azlist.c az_inset) */
#define SG_RAIL_PAD 12       /* the widget is the drawn span plus this much above and below: a tap further from the span reaches the row */
#define SG_RAIL_TEXT_W 24    /* the letters' rect (centred on SG_RAIL_CX, shifted by SG_RAIL_DX, which pod.py derives from the tree's font into stock.h with SG_RAIL_INK2) */
#define SG_LIST_Y 50         /* the list's top in the window (the navbar's height) */
#define SG_RAIL_PITCH 13
#define SG_RAIL_ITEMS 20
#define SG_RAIL_DOT 4
#define SG_RAIL_DOT_RGB 0xff8a8a8au
#define SG_RAIL_DISC 16
#define SG_BUBBLE 110
#define SG_BAR_H 64
#define SG_MAX_SEC 28
#define SG_COLLAPSE 46
#define SG_BUILD_N 64
#define SG_BUILD_MOVE 32
#define SG_MORE_MS 16
#define PH_COVER 160            /* a playlist's header on the Songs page (docs/modules/songs.md "A playlist's header"): the 2 x 2 mosaic of its albums, centred, the album page's cover (160 px, 10 px corners) */
#define PH_COVER_X 80
#define PH_COVER_Y 8
#define PH_COVER_R 10
#define PH_NAME_X 17            /* the name, 22 px white, centred in 286 px (the album page's title label) */
#define PH_NAME_W 286
#define PH_NAME_Y 182           /* 14 px under the cover */
#define PH_NAME_H 22
#define PH_PILL_Y 220           /* the Play pill and Shuffle disc as drawn, 16 px under the name's box (no count line: the count is the list's footer); the rows start SG_TOP - SG_PILL_Y - SG_PILL_H = 12 px under them */
#define PH_BTN_Y 218            /* PH_PILL_Y - (AH_BTN_H - AH_PILL_H) / 2: their 44 px buttons' top (the pill and the disc are drawn centred in them) */
#define PH_TOP 272              /* PH_PILL_Y + SG_PILL_H + 12: where the rows start (SG_TOP is 104 under the large title) */
#define PH_SHIFT 96             /* an artist's page with no photo (patch/albums.c, docs/modules/albums.md): the circle's room, AL_PHOTO_Y + AL_PHOTO_D, is taken out - the name (AL_NAME_Y), the pills (AL_HEAD_PILL_Y), the rows (AL_HEAD_END) and the small title's AL_HEAD_COLLAPSE all move up by it and nothing else changes: the name at y 14, the pills at y 52 (SG_PILL_Y), the block ending at AL_PILLS_END */
#define PH_COLLAPSE 204        /* the navbar shows the small title once the name's box (its bottom, y 204) has scrolled away */
#define SG_FOOT_H 92            /* song count plus three permanent stream-sleep explanation lines under the last row */
#define SG_FOOT_GAP 14
#define SG_FOOT_TEXT_H 20
#define SG_FOOT_PX 15           /* the album page's footer's size, in the secondary grey #AAAAAA */
#define PICKER_ADD 0x10000     /* the stock playlist picker's context is PICKER_ADD | the class listed (the stock Add button @0x52817c: lui 1, or g_class_type) */
#define CONFIRM_KIND_DELETE 3
#define CONFIRM_DELETE_LIBRARY 0xa
#define CONFIRM_DELETE_FILE 0x14
/* The Daily Mix card of the menu's Home instance (patch/dailymix.c, docs/modules/dailymix.md; tools/pod_dailymix.py DM_* are the same numbers, test/pod/dailymix.py
 * asserts it). The section pod_daily (SH_W x DM_SEC_H, a child of the list's scroll view between the shown rows and the Recently Played shelf, hidden and
 * insensitive in the asset): the header pod_dm_head (the shelf's, SH_HEAD_*), the card pod_dm_card (DM_W x DM_H at DM_X, DM_TOP: the shelf's two covers' extent;
 * it paints the art and the text itself), the glass play disc pod_dm_play (DM_DISC square at DM_DISC_X, DM_DISC_Y in the card, a later sibling of the card so it
 * takes its own touches) and two hidden labels that carry the text styles (pod_dm_title 36 px white, pod_dm_sub 16 px #EBEBEB). Text lines: the title in two
 * boxes DM_TITLE_PITCH high at DM_TITLE_Y1 / Y2 (x DM_PAD, DM_TITLE_W wide), the artists in DM_SUB_LINES lines DM_SUB_PITCH apart from DM_SUB_Y, DM_SUB_W wide.
 * The art generator: the scrim ramps in over DM_RAMP rows above DM_ZONE_Y (the first title row). Timing: DM_FIRST_MS after the menu opens the card's files are
 * read; a new mix is made only DM_START_MS after it opened, in slices on the page timer (DM_TICK_MS): DM_SLICE songs a tick, DM_ROWS art rows a tick, DM_ADD
 * playlist songs a tick. DM_LIB_MAX / DM_OFT_MAX / DM_FAV_MAX bound the library, the Most Played and the Favourites lists read; DM_REC_MAX the recent list (the
 * stock keeps 100). Files: the mix (DM_FILE_MAX bytes at most, names DM_NAME bytes) and the art (a 16 byte header and DM_W x DM_H RGB565 words). */
#define CLASS_RECENT 0xf007   /* loadLocalClassList: getAllRecentRecord (newest first, the last 100), getAllOftenRecord (Most Played), getAllFav, getAllPlayList (into *pdeq_playlist) */
#define CLASS_OFTEN 0xf008
#define CLASS_FAV 0xf00a
#define CLASSINFO_ARG 4        /* classinfo[1], the playlist id the Songs page lists (the row tap stores it @0x53d5f4) */
/* Genres and Composers on the Artists page (patch/artists.c, docs/modules/artists.md): the stock Home tiles (where a window that will not open falls back) and the
 * loadLocalClassList class of each (getAllGenre, getAllComposer). A composer's tap is the artist's: loadAlbumList(0xf005, row) leaves class 0xff02 (getAlbumByComposer,
 * the composer's name at classinfo + 0x20d, an "All songs" row last) and its albums' tracks are 0xff14. A genre's tap (the stock row handler @0x535c4c) opens the songs
 * of the genre: class 0xff09 in classinfo[0], the name at classinfo + 0x30d (0x80 bytes), the byte classinfo + 0xc = the row is "Unknown Genre" (id -1). */
#define HOME_GENRE 7
#define HOME_COMPOSER 8
#define CLASS_COMPOSERS 0xf005
#define CLASS_GENRES 0xf006
#define CLASS_COMPOSER_ALBUMS 0xff02
#define CLASS_GENRE_SONGS 0xff09
#define CLASSINFO_GENRE 0x30d
#define CLASSINFO_GENRE_SIZE 0x80
#define CLASSINFO_GENRE_UNKNOWN 0xc
#define NAV_TITLE_SIZE 0x200
#define DM_X 12
#define DM_W 296
#define DM_H 220
#define DM_R 12
#define DM_TOP 44
#define DM_BOTTOM 8
#define DM_SEC_H 272
#define DM_PAD 18
#define DM_TITLE_PX 36
#define DM_TITLE_PITCH 38
#define DM_TITLE_W 260
#define DM_TITLE_Y1 84
#define DM_TITLE_Y2 122
#define DM_SUB_PX 16
#define DM_SUB_PITCH 20
#define DM_SUB_LINES 2
#define DM_SUB_Y 164
#define DM_SUB_W 204
#define DM_DISC 48
#define DM_DISC_X 234
#define DM_DISC_Y 158
#define DM_MAX_NAMES 3
#define DM_BUSY_X 285   /* pod_dm_busy: the 16 px sync glyph (dm_sync, #AAAAAA) in the daily section, centred under the list chevron (x 288..298) and on the header line */
#define DM_BUSY_Y 20
#define DM_ZONE_Y 84
#define DM_RAMP 110
#define DM_FIRST_MS 150
#define DM_TICK_MS 30
#define DM_START_MS 8000
#define DM_SLICE 1536
#define DM_ROWS 20
#define DM_LIB_MAX 12288
#define DM_OFT_MAX 8192
#define DM_FAV_MAX 4096
#define DM_REC_MAX 100
#define DM_FILE_MAX 8192
#define DM_NAME 96
#define DM_PATH 256              /* a song path in the mix file: 1 .. DM_PATH - 1 bytes */
#define DM_ART_HEAD 16
/* The Daily Mix page (patch/dailymix.c dp_*, ui/m1plus_dailymix.bin, tools/pod_dailymix.py DP_* are the same numbers, test/pod/dailymix.py and dmpage.py assert it): an Apple
 * Music playlist page. The window is the list (list_view > scroll_view, DP_VIEW_H = 450 from the window top, no navbar); its one content view paints, in window
 * coordinates, the art (DP_W x DP_ART_H, full width, its last DP_FADE rows fading into the page's solid tint), the centred lines (title DP_TITLE_PX at DP_TITLE_Y,
 * "Made for You" DP_SUB_PX at DP_SUB_Y, the Updated line DP_UPD_PX at DP_UPD_Y: label boxes their font size high, x DP_TEXT_X, DP_TEXT_W wide), then the two buttons
 * (the Shuffle disc DP_SHUF_W x DP_BTN_H at DP_SHUF_X and the Play pill DP_PLAY_W x DP_BTN_H at DP_PLAY_X, both at DP_BTN_Y; the pill is drawn DP_PILL_H high, the
 * glyph DP_PILL_GLYPH + DP_PILL_GAP + the text centred in it), the description (up to DP_DESC_LINES lines DP_DESC_PITCH apart from DP_DESC_Y, DP_TEXT_W wide), and the
 * songs from y rows_y = DP_DESC_Y + lines * DP_DESC_PITCH + DP_DESC_BELOW, LIST_ROW_H each, exactly the Albums list's: the LIST_ART px cover at LIST_ART_X
 * (LIST_ART_Y down, LIST_R corners), the title and artist (LIST_TITLE_Y / LIST_SUB_Y) at LIST_TEXT_X, LIST_TEXT_W wide, a hairline from LIST_TEXT_X
 * on. The tint: the art's last row averaged, its brightest channel lifted to DP_V_MIN, darkened by 15/16 steps until its 16 bit luminance is at most DP_LUM_MAX, snapped to
 * 565; the grey and accent lines are the tint lightened by DP_GREY_K / DP_ACC_K of 256 towards white. DP_BACK_*: the glass back disc (DP_BACK_DISC) in its DP_BACK_BTN touch square. */
#define DP_W 320
#define DP_ART_H 180
#define DP_FADE 60
#define DP_HOLD 4               /* the last rows of the art are the tint's own word: the fade reaches it DP_HOLD rows before the end */
#define DP_VIEW_H 450
#define DP_BACK_BTN 44
#define DP_BACK_X 8
#define DP_BACK_Y 8
#define DP_BACK_DISC 40
#define DP_TEXT_X 16
#define DP_TEXT_W 288
#define DP_TITLE_PX 24
#define DP_SUB_PX 17
#define DP_UPD_PX 14
#define DP_DESC_PX 15
#define DP_TITLE_Y 193
#define DP_SUB_Y 218
#define DP_UPD_Y 239
#define DP_BTN_Y 263
#define DP_BTN_H 44
#define DP_SHUF_X 32            /* Shuffle disc | Play pill | Add disc, symmetric about x 160: drawn 40 px discs and a 148 px pill 12 px apart (34 .. 286) */
#define DP_SHUF_W 44
#define DP_PLAY_X 86
#define DP_PLAY_W 148
#define DP_ADD_X 244            /* the Add disc (saves the mix as a stock playlist), the Shuffle disc mirrored: DP_SHUF_X + DP_ADD_X + DP_ADD_W = 320 */
#define DP_ADD_W 44
#define DP_PILL_H 40
#define DP_PILL_GLYPH 16
#define DP_PILL_GAP 8
#define DP_DESC_Y 317
#define DP_DESC_PITCH 20
#define DP_DESC_LINES 2
#define DP_DESC_BELOW 14
#define DP_ROWS_Y 371           /* DP_DESC_Y + DP_DESC_LINES * DP_DESC_PITCH + DP_DESC_BELOW: the first song's row (the description reserves two lines in every language) */
#define DP_BOTTOM 16
#define DP_V_MIN 48
#define DP_LUM_MAX 4588
#define DP_PILL_INK 0x141414u     /* the pill's dark text (the glyph is the album page's image ah_play, the same colour AH_PLAY_INK): #141414 as r | g << 8 | b << 16 */
#define DP_GREY_K 184
#define DP_ACC_K 208
#define DP_ROWS_MAX 64          /* songs the page keeps (the mix has MIX_SONGS; a playlist of ours cannot have more, but a rename-proof id could meet a longer one) */
#define DP_PRESS 0x33ffffffu    /* a pressed row: 20 % white over the tint */
#define DP_HAIR 0x22ffffffu     /* the hairline under a row: 13 % white */
#define DP_MORE_MS 16           /* the cover loader's tick (the Albums list's) */
/* The mix (tools/pod_mix.py is the model, test/pod/dailymix.py compares it with the compiled code): MIX_SONGS songs from a library of at least MIX_MIN_LIB
 * playable songs (else no mix), at most MIX_PER_ARTIST of one artist and MIX_PER_ALBUM of one album; when that leaves the mix short, MIX_PER_ARTIST2 and
 * MIX_PER_ALBUM2, then no limit (a library of few artists or albums still gets a full mix); an untagged artist or album is the song's folder; fewer than
 * MIX_MIN_SONGS whose files exist: no mix. Score = MIX_W_PLAYS * lg(plays, capped at MIX_PLAYS_CAP) + MIX_W_ARTIST * lg(the artist's
 * plays over the library, capped at MIX_ARTIST_CAP) + novelty (MIX_NOVEL0 never played, MIX_NOVEL1 once) + MIX_W_FAV if a favourite - MIX_W_RECENT * (100 - position)
 * / 100 for a song among the last 100 played (position 0 = the last one) + a day-seeded jitter of 0 .. MIX_JITTER - 1; lg(n) = 16 * log2(1 + n) in fixed point. */
#define MIX_SONGS 25
#define MIX_MIN_SONGS 10
#define MIX_PER_ARTIST 2
#define MIX_PER_ALBUM 2
#define MIX_PER_ARTIST2 4
#define MIX_PER_ALBUM2 3
#define MIX_MIN_LIB 50
#define MIX_W_PLAYS 4
#define MIX_W_ARTIST 2
#define MIX_NOVEL0 60
#define MIX_NOVEL1 30
#define MIX_W_FAV 50
#define MIX_W_RECENT 160
#define MIX_JITTER 128
#define MIX_PLAYS_CAP 200
#define MIX_ARTIST_CAP 4000
#define MIX_ALBUMS 3

/* The virtual iPod Classic page (patch/ipod.c, docs/modules/ipod.md; tools/pod_ui.py build_ipod_page and tools/mod_icons.py ipod_wheel build the asset from
 * the same numbers). A fullscreen window (320 x 480, the status bar is not drawn): the iPod screen on top (IP_BAR_H title bar, IP_ROWS rows of IP_ROW_H), the click wheel
 * below (a IP_WHEEL_D image at IP_WHEEL_X, IP_WHEEL_Y; the touch circle is IP_RING_R, the centre button IP_HUB_R). Colours are r | g << 8 | b << 16 words. */
#define IP_W 320
#define IP_SCREEN_H 240
#define IP_BAR_H 24
#define IP_ROW_H 30               /* a text row: 18 px bold text */
#define IP_ROWS 7                 /* 24 + 7 x 30 = 234 of the 240 px: no partial row */
#define IP_TALL_H 54              /* a cover row (Albums, Songs, Playlists): a 52 px cover, 18 px bold title over a 16 px subtitle */
#define IP_TALL_ROWS 4            /* 24 + 4 x 54 = 240 */
#define IP_SPLIT_X 160            /* split menu and cover pane */
#define IP_WHEEL_X 50
#define IP_WHEEL_Y 250
#define IP_WHEEL_D 220
#define IP_RING_R 110
#define IP_HUB_R 45
#define IP_DEAD_R 11              /* a move whose chord passes closer than this to the centre (10% of IP_RING_R) turns nothing: the angle jumps there */
#define IP_STEP 240               /* one wheel step = 15 degrees (24 a turn), in sixteenths of a degree: THE tuning constant of the feel */
#define IP_REVERSE 128            /* after the drag flips direction, this much reverse travel (8 degrees) is swallowed before stepping resumes */
#define IP_LONG 16                /* a list of more rows than this accelerates; this many or fewer always move one row a step */
#define IP_VMAX 6400              /* the instantaneous angular speed is clamped here before smoothing: 400 degrees a second, in sixteenths */
#define IP_SMOOTH_NUM 3           /* angular speed smoothing: v += (min(instant, IP_VMAX) - v) * 3 / 20 (0.15) */
#define IP_SMOOTH_DEN 20
#define IP_FAST 2880              /* smoothed speed above which the tiers climb: 180 degrees a second, in sixteenths */
#define IP_PAUSE_MS 250           /* a gap this long between two moves resets the speed and the tier */
#define IP_TIER_MS 500            /* held above IP_FAST this long climbs one tier */
#define IP_TAP_PX 12              /* a touch that travels less than this and turns no step is a tap */
#define IP_LONG_MS 500            /* MENU held this long pops to the main menu (the reference's long press) */
#define IP_ART 150                /* the Now Playing screen's picture */
#define IP_TICK_MS 500
#define IP_FIRST_MS 50
#define IP_DEPTH 7
#define IP_TEXT_X 8
#define IP_SEL_TOP 0xf7b15fu      /* the classic blue selection: #5FB1F7 to #0C62D2, top to bottom (as r | g << 8 | b << 16) */
#define IP_SEL_BOT 0xd2620cu
#define IP_NP_ART_X 10
#define IP_NP_ART_Y 30
#define IP_NP_REFLECT 20          /* rows of the cover's reflection under it (30 % fading to 0): cover y 30 .. 180, reflection to 200, the bar from 208 */
#define IP_MODE_PX 16             /* the play mode mark (shuffle, repeat, repeat one): a 16 px image, right edge at x 312, top y 28 (the reference's 13 pt heavy SF symbols) */
#define IP_PLAY_PX 14             /* the playing track speaker (Lucide volume-2) in a plain song list: right aligned at IP_W - IP_TEXT_X, centred in its row */
#define IP_MODE_X 296
#define IP_MODE_Y 28
#define IP_NP_TEXT_X 176
#define IP_NP_BAR_Y 208
#define IP_NP_BAR_H 14            /* the progress track: 14 px, x 58 .. 262 between 50 px time columns (8 px apart), with a short reflection (IP_NP_BAR_REFLECT) under it */
#define IP_NP_TRACK_X 58
#define IP_NP_TRACK_W 204
#define IP_NP_BAR_REFLECT 6
/* The split pages' cover pane (patch/ipod.c, docs/modules/ipod.md "The cover pane"): the pane starts flush at IP_SPLIT_X (no rule between the white menu and the cover), under the title bar.
 * Covers are scaled once to IP_PANE_ART (the pane's height zoomed 110%) and copied 1:1 into it: a linear pan across the zoom's margin
 * (IP_PANE_R px), in whole pixels, so nothing is resampled while it moves; the next cover cross-fades in every IP_PANE_HOLD_MS. */
#define IP_PANE_X 160
#define IP_PANE_W 160
#define IP_SHADOW_W 10            /* the white menu casts a soft shadow on the pane's left edge (a real iPod's, iPlayr's radius 8, offset 4): IP_SHADOW_W columns, black, 52 % at the edge falling to 0 (the table in ip_shadow_alpha) */
#define IP_PANE_H 240
#define IP_PC_GLYPH_Y 104         /* the main menu's Podcasts pane (ipod_podcasts, IP_PANE_W x IP_PANE_H): the glyph's centre (tools/mod_icons.py), and the top of the 30 px row No Podcasts is centred in */
#define IP_PC_TEXT_Y 160
#define IP_PANE_ART 264
#define IP_PANE_R 24
#define IP_PANE_TRIES 48          /* random albums looked at (one cache file test each) for the cover shown while nothing with a cached cover plays */
#define IP_DRIFT_MS 100           /* the page timer's interval while the cover pans on the main menu (IP_TICK_MS otherwise) */
#define IP_PANE_KEYS 8            /* the random albums that rotate through the pane */
#define IP_PANE_PAN_MS 7500       /* each cover pans linearly across the margin in this time, every other one the other way (the reference's 7.5 s, +-8% of the pane) */
#define IP_PANE_HOLD_MS 6000      /* the next cover starts to fade in this long after the last one did */
#define IP_PANE_FADE_MS 1500      /* the cross-fade, ease in and out */
#define IP_PANE_NEXT_MS 3000      /* the next cover is decoded this long after the last fade began (a tick of its own, well before the next fade) */
#define IP_PANE_SHARP_MS 4000     /* the playing album's full-resolution file is trusted this long after a track change even when demo was not seen making it (a stale file of the last track is never shown) */
#define IP_FADE_TICK_MS 50        /* the timer's interval during a cross-fade (each frame is one pass over the 160 x 240 pane with two interpolations and a mix) */
#define IP_PAN_MS 40              /* ... and while the cover pans: a steady 25 frames a second, each a sub-pixel step (IP_DRIFT_MS stays the pace of the other fast jobs) */
#define IP_DRIFT_MAX_MS 250       /* a step is capped at this, so a stalled loop never jumps */
#define IP_DRIFT_LOOK 12          /* while the pan ticks, the clock / battery / track look runs every this many ticks (about half a second) */

/* Podcasts (patch/pcmodel.c, patch/podcasts.c, docs/modules/podcasts.md). Files the user copies to /mnt/mmc/Podcasts/<Show>/; the episode model, the resume ring and the speeds
 * are pcmodel.c, the page is podcasts.c. pc_ep_t / pc_show_t are the model's records (test/pod/podcasts.py reads them by these offsets; pcmodel.c asserts the sizes). */
#define PC_FILE 128               /* a file or folder name, the NUL included (a longer name is skipped: it would not fit the path buffers) */
#define PC_TITLE 96               /* a title, UTF-8 bytes with the NUL (cut before a continuation byte) */
#define PC_URL 320                /* a feed or image url of the show file (the feed url the refresh fetches: a longer one is refused at import) */
#define PC_MAX_EPS 300            /* episodes of one show the model holds (newest kept) */
#define PC_MAX_SHOWS 100          /* shows the page holds: the Shows grid has the first PP_SHOWS_MAX, the All Shows page every one */
#define PC_DESC 208               /* a description: at most PC_DESC_CUT bytes of UTF-8 (cut before a continuation byte) and the NUL, with room */
#define PC_DESC_CUT 200           /* the bytes of a description the feed reader keeps (HTML stripped, entities decoded, white space collapsed) */
#define PC_AUTHOR 64              /* a show's author (itunes:author), UTF-8 bytes with the NUL */
#define PC_CAT 48                 /* a show's first iTunes category, UTF-8 bytes with the NUL */
#define PC_EP_SIZE 456            /* pc_ep_t: file[PC_FILE] title[PC_TITLE] guid pub dur length hash state desc[PC_DESC] */
#define PC_EP_DESC 248
#define PC_EP_TITLE 128
#define PC_EP_GUID 224
#define PC_EP_PUB 228
#define PC_EP_DUR 232
#define PC_EP_LENGTH 236
#define PC_EP_HASH 240
#define PC_EP_STATE 244
#define PC_LOCAL 0                /* pc_ep_t.state: the file is on the card */
#define PC_PART 1                 /* a .part file only (a download under way or cut off) */
#define PC_REMOTE 2               /* metadata only: not downloaded */
#define PC_SHOW_SIZE 1336         /* pc_show_t: dir[PC_FILE] title[PC_TITLE] cover[PC_FILE] feed[PC_URL] image[PC_URL] count hash fresh checked author[PC_AUTHOR] category[PC_CAT] desc[PC_DESC] newest modified */
#define PC_SH_NEWEST 1328         /* the newest episode's date (seconds since 1970; an entry's p=, remote or local; the files' dates when there is no .episodes), 0 = none: the Shows page's order */
#define PC_SH_MODIFIED 1332       /* the show file's modified=: the server's Last-Modified of the feed we hold, 0 = none */
#define PC_SH_AUTHOR 1008
#define PC_SH_CAT 1072
#define PC_SH_DESC 1120
#define PC_SH_TITLE 128
#define PC_SH_COVER 224
#define PC_SH_FEED 352
#define PC_SH_IMAGE 672
#define PC_SH_COUNT 992
#define PC_SH_HASH 996
#define PC_SH_CHECKED 1004        /* seconds since 1970 of the last successful refresh (the show file's checked=), 0 = never */
#define PC_SH_NEW 1000            /* episodes with no saved place and not played (the dot count), set by pc_load_show_counts */
#define PC_RING_SLOTS 4096        /* places kept (two lists of PC_ALL_MAX: Mark All as Played on a show with an archive keeps every mark; a file of fewer slots, as the 512 of before, is read as it is); a slot is 16 bytes: hash, pos, len, flags */
#define PC_SLOT_SIZE 16
#define PC_RING_HEAD 8            /* "PCR1" and the slot count */
#define PC_SPEED_SLOTS 64         /* per-show speed modes: 8 bytes each (show hash, mode), after "PCS1" and the count */
#define PC_EDGE_S 30              /* within this many seconds of either end a place is forgotten (q2-pod RESUME_EDGE_S): near the start nothing is saved, near the end the episode is played */
#define PC_SAVE_MS 30000          /* the ring is written at most this often while an episode plays (also at a track change, a pause and the page's own actions) */
#define PC_SEEK_MAX 5             /* a saved place is jumped to only while the episode has played less than this (q2-pod RESUME_START_S) */
#define PC_SEEK_WAIT_MS 15000     /* a seek that has not happened this long after the episode started is dropped */
#define PC_COVER_MAX_PX 2100000   /* a cover picture is decoded only when width * height is at most this (the stock loader holds the whole bitmap) */
#define PC_ROW_H 64               /* the page's rows (LIST_ROW_H) */
#define PC_TILES 44               /* text / cover tiles: the rows and cells in view and spare (a ring: the least recently used leaves) */
#define PC_SPEEDS 4               /* playspeed_mode 0..3: 1x, 1.25x, 1.5x, 2x (stock "Multiple Speed", images p_1_25 / p_1_5 / p_2) */
/* The Podcasts Show page (patch/podcasts.c, docs/modules/podcasts.md "The Show page"; tools/preview/preview_podcasts_revamp.py reads these). Content y is from the list's top (window row
 * PG_LIST_Y = the navbar's bottom), x is the window's. HEADER, in the album page's and the playlist header's manner: the PS_ART px cover at x PS_ART_X with PS_ART_R px corners (flush with
 * the list's top: the album page's 50), the show's name PS_NAME_GAP under it (PS_NAME_PX white, centred in PS_NAME_X / PS_NAME_W, PS_NAME_PITCH a line, at most PS_NAME_LINES), the
 * Latest Episode pill PS_LATEST_GAP under that (PS_LATEST_H high, white, centred: its ends the white disc, PS_LATEST_PADL / glyph / PS_LATEST_GAPG / text / PS_LATEST_PADR), the
 * show's description (PS_DESC_GAP under the pill, PS_DESC_LINES lines of PS_DESC_PITCH, PS_DESC_X / PS_DESC_W), the "Category · Author" line (PS_META_GAP under it) and the Episodes header
 * (PS_HEAD_GAP under the last block, PS_HEAD_H high). The navbar's small title shows once the offset passes the name's bottom less PS_COLLAPSE_BACK. CELLS are PS_CELL_H high, in the
 * order of the offsets below (from the cell's top); the state pill is PS_PILL_H high from x PS_CELL_X (pad PS_PILL_PADL, the PA_G_PX glyph, PS_PILL_GAP, the text, PS_PILL_PADR); the
 * "..." is PS_DOTS_HIT px square around (PS_DOTS_CX, the pill's middle). BADGES on the date line: the check (a PA_G_PX cell, PS_BADGE_CHECK_W wide slot) when played, the PA_BADGE_PX disc
 * (PS_BADGE_DISC_W slot) when the file is on the card. PA_* is the atlas pc_atlas (tools/mod_icons.py PA_*): PA_RING_N 12-step progress rings, PA_G_* the 16 px glyph strip. */
#define PG_LIST_Y 50
#define PS_ART 160
#define PS_ART_X 80
#define PS_ART_R 10
#define PS_NAME_GAP 14
#define PS_NAME_PX 22
#define PS_NAME_PITCH 26
#define PS_NAME_X 17
#define PS_NAME_W 286
#define PS_NAME_LINES 2
#define PS_LATEST_GAP 12
#define PS_LATEST_H 40
#define PS_LATEST_PADL 18
#define PS_LATEST_GLYPH 14
#define PS_LATEST_GAPG 8
#define PS_LATEST_PADR 20
#define PS_LATEST_MAX 296
#define PS_DESC_GAP 14
#define PS_DESC_PITCH 21
#define PS_DESC_LINES 2
#define PS_DESC_X 16
#define PS_DESC_W 288
#define PS_META_GAP 6
#define PS_META_PITCH 22
#define PS_HEAD_GAP 14
#define PS_HEAD_H 34
#define PS_COLLAPSE_BACK 12
#define PS_CELL_H 173
#define PS_MORE_H 56              /* the See All row under the last cell of the Show page (docs/modules/podcasts.md "All episodes") */
#define PS_SHOW_MAX 20            /* rows of the recent list the Show page paints; See All opens the page with every episode */
/* The busy row's spinner (the See All row while its job runs, and the search's Search All Episodes row): the Wi-Fi page's wf_spin frames, PS_SPIN_PX square, PS_SPIN_GAP before the text, turned every PS_SPIN_MS by the page's own timer. */
#define PS_SPIN_PX 14
#define PS_SPIN_GAP 8
#define PS_SPIN_MS 250
#define PS_PCELL_H 137            /* the preview's cell (docs/modules/podcasts.md "Search"): the date line, the title and the description of a normal cell without the pill row: PS_CDESC_Y + 2 * PS_CDESC_PITCH + 14 under it */
#define PS_CELL_X 16
#define PS_CELL_W 288
#define PS_DATE_Y 9
#define PS_DATE_H 22
#define PS_TITLE_Y 32
#define PS_TITLE_PITCH 24
#define PS_CDESC_Y 83
#define PS_CDESC_PITCH 20
#define PS_PILL_Y 131
#define PS_PILL_H 30
#define PS_PILL_PADL 10
#define PS_PILL_GAP 6
#define PS_PILL_PADR 12
#define PS_DOTS_CX 292
#define PS_DOTS_HIT 44
#define PS_BADGE_CHECK_W 20
#define PS_BADGE_DISC_W 18
#define PS_SHEET_ICON_X 14
#define PS_SHEET_TEXT_X 48
#define PS_SHEET_VALUE_R 304
#define PS_SHEET_VALUE_W 130
#define PS_SHEET_GAP 12
#define PA_SIZE 160
#define PA_RING_PX 16
#define PA_RING_N 12
#define PA_RING_COLS 6
#define PA_G_Y 32
#define PA_G_PX 16
#define PA_ARROW 0
#define PA_PLAY 1
#define PA_PAUSE 2
#define PA_RETRY 3
#define PA_CHECK 4
#define PA_PLAYK 5
#define PA_DOTS_Y 48
#define PA_DOTS_PX 20
#define PA_BADGE_X 24
#define PA_BADGE_PX 12
#define PA_DSD_X 40 /* the source rows' DSD tag (sbs_marks): 24 x 14, grey */
#define PA_DSD_Y 48
#define PA_DSD_W 24
#define PA_DSD_H 14
#define PA_PILL_Y 68
#define PA_PILLF_X 0
#define PA_PILLO_X 32
#define PA_PILLW_X 64
#define PA_PILLR_X 108
#define PA_PILL_PX 30
#define PA_PILLW_PX 40
#define PA_FILL_A 56
#define PA_RING_A 110
#define PA_TRACK_A 80 /* the progress ring's track alpha (white; the arc is white at more): under an accent a pixel above it is arc, in the accent (patch/podcasts.c pg_ring_tint) */
#define PA_DL_TRACK_R 90 /* the download ring's track grey (0x5A) and its arc's (0xD0, the downloaded disc's): a ring pixel's grey says how much of it is arc, which goes to the accent (patch/libsrc.c ls_ring_tint) */
#define PA_DL_ARC_R 208
#define PA_CHEV 6
#define PA_TILE_PX 44
#define PA_DL_X 76 /* the source rows' download ring (patch/libsrc.c): 12 steps of PA_DL_PX, step k at column k % PA_DL_COLS, row k / PA_DL_COLS from here */
#define PA_DL_Y 112
#define PA_DL_PX 14
#define PA_DL_N 12
#define PA_DL_COLS 6
#define PA_DL_ARROW 12 /* the marks, on the same grid after the steps: the arrow-down (a queued track) and the stop square (a running download, over its step) */
#define PA_DL_STOP 13
#define PA_PLAYB_X 48
#define PA_PLAYB_Y 112
#define PA_PLAYB_PX 28
/* The Podcasts Shows page (Apple Podcasts style; patch/podcasts.c, docs/modules/podcasts.md "The Shows page"; tools/pod_show.py shows_layout is the model the tests and tools/preview/preview_podcasts_revamp.py use). Content y from the list's top
 * (window row PG_LIST_Y), x the window's. In order: the large title (a label, PP_TITLE_H high at x SG_TITLE_X, SG_TITLE_W wide, PP_TITLE_PX px, shared by the Downloads, Subscriptions and Saved pages; it scrolls away with the content and the navbar shows the small title past SG_COLLAPSE), the refresh line (PP_LINE_H high at PP_LINE_Y, 15 px: "Updated
 * 1h ago", a status with no control (Refresh All is a row of the "..." sheet), only when a show has a feed; PP_LINE_PITCH to the next block, PP_NOLINE_PITCH when there is no line), Continue Listening (PP_HEAD_H header at x PP_HEAD_X, 20 px, then PP_HEAD_PITCH to the
 * covers: at most PP_SHELF_MAX PP_SHELF_ART px covers at x PP_SHELF_X + i * PP_SHELF_PITCH, the title (14 px, one line, PP_SHELF_W wide) PP_SHELF_TITLE_Y under the cover's top and the "35m left" (13 px) at PP_SHELF_LEFT_Y; PP_SHELF_PITCH_Y the block's height; each cover has the atlas' PA_PLAYB_PX play disc PP_SHELF_PLAY_INSET from its right and bottom edges),
 * the Library rows, last, PP_LIB_GAP under the grid (Search while Podcast Search is on, Downloads, Subscriptions, Saved; the Downloads row: PC_ROW_H high: the PA_TILE_PX tile (an image of its own) at x PP_DL_TILE_X, PP_DL_TILE_Y down, the texts from PP_DL_TEXT_X, PP_DL_TEXT_W wide at LIST_TITLE_Y / LIST_SUB_Y, the shared chevron at PP_DL_CHEV_X, hairline from the text),
 * after the shelf PP_SEC_GAP of air and the "Shows" header (at x PP_SHOWS_X), then the Albums grid (GRID_*: GRID_COVER covers, the title and the grey line under each) from the grid's top; PP_BOTTOM under the last row. */
#define PP_TITLE_H 52
#define PP_TITLE_PX 32
#define PP_LINE_Y 52
#define PP_LINE_H 20
#define PP_LINE_PITCH 34
#define PP_NOLINE_PITCH 8
#define PP_LINE_X 12 /* = SG_TITLE_X: the grey line under a large title starts under the title */
#define PP_HEAD_H 28
#define PP_HEAD_PITCH 34
#define PP_HEAD_X 14
#define PP_SHOWS_X 12 /* = GRID_MARGIN, SG_TITLE_X: the header starts where the covers under it and the large title do */
#define PP_SHELF_MAX 3
#define PP_SHELF_ART 92
#define PP_SHELF_R 8
#define PP_SHELF_X 14
#define PP_SHELF_PITCH 100
#define PP_SHELF_W 92
#define PP_SHELF_TITLE_Y 96
#define PP_SHELF_TITLE_H 18
#define PP_SHELF_LEFT_Y 114
#define PP_SHELF_LEFT_H 16
#define PP_SHELF_PITCH_Y 142
#define PP_SHELF_PLAY_INSET 6
#define PP_DL_TILE_X 16
#define PP_DL_TILE_Y 10
#define PP_DL_TEXT_X 72
#define PP_DL_TEXT_W 206 /* the text ends at x 278 (72 + 206), 10 px before the shared chevron */
#define PP_DL_CHEV_X 288 /* = LIST_CHEV_X: the shared chevron (m1_make_chevron), centred on the row above its hairline */
#define PP_SEC_GAP 12
#define PP_SHOWS_MAX 10 /* the grid's shows (the most recently updated); with more, a See All (N) row (PS_MORE_H high, its text at PP_SHOWS_X) is under the grid in place of PP_LIB_GAP and opens the All Shows page */
#define PP_LIB_GAP 24 /* the air between the grid's last row and the Library rows (Search, Downloads, Subscriptions, Saved) that close the Shows page */
#define PP_BOTTOM 10
/* The Downloads page (patch/podcasts.c, docs/modules/podcasts.md "The Downloaded page"; tools/pod_show.py downloads_layout is the model): content y from the list's top. The storage line (15 px grey, PP_LINE_H high) at PDL_LINE_Y, x PP_LINE_X;
 * the first section's header PDL_LINE_PITCH down; a section is its header (PP_HEAD_PITCH) and its PC_ROW_H rows; PP_SEC_GAP between sections; PP_BOTTOM under the last row. The Library rows of the Shows page are the Downloads row's geometry
 * twice (PP_DL_*): Downloads, then Subscriptions (its tile is the image pod_ic_subtile, PA_TILE_PX square). */
#define PDL_LINE_Y 52
#define PDL_LINE_PITCH 80

/* The segmented control (patch/common.c m1_segmented, docs/modules/ui-rules.md "Segmented control"; the Discover level's Shows | Episodes is the first): a fully rounded track (SEG_TRACK, #1C1C1E, as the cards) holding equal segments, the selected one a
 * fully rounded thumb (SEG_THUMB, #D1D1D6, black label) SEG_PAD inside the track on every side, the other labels white; a SEG_SEP (#3A3A3C) hairline half the track high between two unselected segments. Colours are color_t words (r, g, b, a bytes). */
#define SEG_PAD 3
#define SEG_TRACK 0xff1e1c1cu /* the surface #1C1C1E */
#define SEG_THUMB 0xffd6d1d1u
#define SEG_SEP 0xff3c3a3au
#define SEG_LABEL_H 20 /* the label's rect: 18 px text */
/* The Podcasts Discover level (patch/podcasts.c, docs/modules/podcasts.md "Discover"; tools/pod_show.py discover_layout is the model the tests and the preview use). Content y from the list top (window row PG_LIST_Y): the large title (PP_TITLE_H),
 * the grey line under it (15 px, the Downloads storage line's place: x PP_LINE_X, PDL_LINE_Y, PP_LINE_H high), the Shows | Episodes control (the segmented control, SEG_*, at x DC_SEG_X, DC_SEG_Y, DC_SEG_W x DC_SEG_H), then from DC_TOP the ranked rows, PC_ROW_H each, the list painter shifted DC_SHIFT right for the rank (18 px grey, right aligned to DC_RANK_END): the cover at x 36, the text
 * 100 to 278, the chevron at LIST_CHEV_X, the hairline 100 to 310. DC_BOTTOM under the last row. */
#define DC_SEG_X 12 /* = SG_TITLE_X: under the large title, to x 308 */
#define DC_SEG_Y 80
#define DC_SEG_W 296
#define DC_SEG_H 36
#define DC_TOP 128
#define DC_SHIFT 26
#define DC_RANK_END 28
#define DC_BOTTOM 10

/* The Podcasts search level (patch/podcasts.c, docs/modules/podcasts.md "Search"; tools/pod_show.py search_layout is the model the tests and the preview use). Content y from the list top (window row PG_LIST_Y). The field is widgets of the content view
* (ps_field, the keyboard page's field look: PQ_FIELD_W x PQ_FIELD_H, #1C1C1E, PQ_FIELD_R corners, the 16 px magnifier PQ_MAG_X in, the text from PQ_TEXT_X for PQ_TEXT_W px); the result rows are the Downloads rows' (PC_ROW_H, a LIST_ART px
* cover, the name, the author in grey) from PQ_TOP; a result with no feed is dimmed (PQ_DIM, an ARGB black over the row). The Subscribe pill of the preview is at least PQ_SUB_MIN wide. */
#define PQ_FIELD_X 10 /* the keyboard page's field (tools/pod_keyboard.py FIELD_*): x, w, the magnifier and the text are the same numbers, y is the same on screen (PG_LIST_Y + PQ_FIELD_Y = 58), so the glyph does not move when the keyboard page opens */
#define PQ_FIELD_Y 8
#define PQ_FIELD_W 300
#define PQ_FIELD_H 36
#define PQ_FIELD_R 10
#define PQ_MAG_X 8
#define PQ_MAG 16
#define PQ_TEXT_X 30
#define PQ_TEXT_W 228
#define PQ_CLEAR_X 264 /* the clear button's 36 px touch area in the field (the 16 px disc centred in it); shown with a text */
#define PQ_CLEAR_W 36
#define PQ_CLEAR 16
#define PQ_TOP 52
#define PQ_BOTTOM 16
#define PQ_DIM 0x99000000u
#define PQ_SUB_MIN 150

/* The Tape page (patch/tape.c, docs/modules/tape.md; tools/tape_art.py draws the images from the same numbers, test/pod/tape.py checks them). The page is LANDSCAPE, 480 x 320: the
 * framebuffer is the portrait 320 x 480 and holds the picture turned 90 degrees clockwise, so landscape (x, y) is the framebuffer's row x, column 319 - y. Everything below is in
 * landscape pixels. Colours are r | g << 8 | b << 16 words (alpha ff added by the code). */
#define TP_W 480                  /* landscape width = framebuffer rows */
#define TP_H 320                  /* landscape height = framebuffer columns */
#define TP_TOP_X 100              /* tape_top's rectangle (landscape): the holes with their rings, the clear window; turned it is 74 columns x 280 rows */
#define TP_TOP_Y 110
#define TP_TOP_W 280
#define TP_TOP_H 74
#define TP_REEL_X0 132            /* the reels' centres (landscape, on a pixel boundary): supply, take-up, and their y */
#define TP_REEL_X1 348
#define TP_REEL_Y 147
#define TP_HOLE_R 28
#define TP_HUB_R 14
#define TP_HUB_PX 30              /* a hub sprite's cell in tape_hubs: 24 stacked, 5 degrees apart (the ring has 6 teeth, the drive 3 spokes: the picture repeats every 120 degrees) */
#define TP_SPRITES 24
#define TP_PACK_MIN 16            /* the tape pack's radius on an empty and on a full reel; r_supply^2 + r_takeup^2 is constant (the tape's area) */
#define TP_PACK_MAX 66
#define TP_CLEAR_X0 180           /* the clear window (x0, y0 inclusive, x1, y1 exclusive) and its corner radius */
#define TP_CLEAR_Y0 112
#define TP_CLEAR_X1 300
#define TP_CLEAR_Y1 182
#define TP_CLEAR_R 4
#define TP_MARK_PX 26             /* a printed mark's cell in tape_marks (play, pause, repeat stacked) and where it is on the band: the cells' top left */
#define TP_PLAY_X 410
#define TP_PLAY_Y 115
#define TP_REPEAT_X 410
#define TP_REPEAT_Y 153
#define TP_SPIN 76800             /* the reels' speed: angular speed x pack radius, in 1/16 degree x px a second (300 degrees a second at the empty pack's 16 px) */
#define TP_PLAY_MS 70             /* the page timer's interval while playing (the reels turn) and paused */
#define TP_IDLE_MS 500
#define TP_FIRST_MS 50
#define TP_TAP_PX 14              /* a touch that travels less than this (landscape pixels) is a tap */
#define TP_CLOSE_X0 0             /* the close button, the top left screw as the user sees it (landscape): a 50 x 50 touch area around it, x1 / y1 exclusive */
#define TP_CLOSE_Y0 0
#define TP_CLOSE_X1 50
#define TP_CLOSE_Y1 50
#define TP_SCREW_X 11             /* its pressed sprite tape_screw (MARK_PX square): its top left on the screen */
#define TP_SCREW_Y 12
#define TP_LUT_N 18500            /* the distance table: sqrt(d2h) for d2h = (2 dx + 1)^2 + (2 dy + 1)^2 up to this, in 1/16 px */
#define TP_THEME_AUTO 3           /* the saved theme "by the track's quality": lossy Normal, lossless Chrome, hi-res and DSD Metal (the page's own theme is always 0 .. 2) */
#define TP_INFO_MS 600            /* the longest the page holds the last track after a change of track, waiting for the player's record to be the new track's (then it is taken as it is) */
#define TP_BADGE_X 33             /* the sticker tape_badge (TP_BADGE_W x TP_BADGE_H) on the shell, its top left; HI-RES or DSD is written on it */
#define TP_BADGE_Y 237
#define TP_BADGE_W 52
#define TP_BADGE_H 24
#define PLAYINFO_BITRATE 0        /* mclGetInfo's record (0x34 bytes): bit/s, Hz, the codec's name (0x20 bytes), bits a sample (1: DSD) */
#define PLAYINFO_RATE 4
#define PLAYINFO_POS 8            /* the position and the length: mclSyncPlayerStatus (0x5d144c) rewrites the whole record from the player's reply every 200 ms in one lock section; mclStartPlayer, */
#define PLAYINFO_LEN 0xc          /* mclNextSong and mclPrevSong zero only these two (under the mutex) when another track is started, rate, bits and name stay the last track's until a poll answers */
#define PLAYINFO_FMT 0x10
#define PLAYINFO_BITS 0x30
#define PLAYINFO_SIZE 0x34

/* ---------------------------------------------------------------------------
 * Regional CJK forms (patch/fontregion.c, docs/modules/fonts.md "Regional forms"). The AWTK stb font object
 * (font_stb_create_ex 0x67ee74, tk_calloc(1, 0xd4) @0x67ef14): font_t then stbtt_fontinfo at +0x38.
 * ------------------------------------------------------------------------- */
#define FONT_MATCH 0x20           /* font_t match: 0x67d2d4 for an stb font (sw @0x67ef48), name only, size ignored */
#define FONT_GET_GLYPH 0x24       /* font_t get_glyph: font_stb_get_glyph 0x680228 (sw @0x67ef60) */
#define FONT_DATA 0x3c            /* stbtt_fontinfo data: the ttf buffer (sw s7 @0x67f030) */
#define FONT_START 0x40           /* stbtt_fontinfo fontstart (sw s6 @0x67f038) */
#define FONT_INDEX_MAP 0x64       /* stbtt_fontinfo index_map: cmap + the chosen subtable offset, from data (sw @0x67f758); */
                                  /* stbtt_FindGlyphIndex reads data and it on every call (lw 4(a0), 0x2c(a0) @0x67c3c0) */
#define STB_MATCH 0x67d2d4u
#define STB_GET_GLYPH 0x680228u
#define FONT_CACHE 0xb4           /* font_t glyph cache (the argument of glyph_cache_lookup; sw/addiu @0x6802d8) */
#define FONT_MONO 0xd0            /* font_t mono flag: 1-bit glyphs (lbu @0x680458); patch/textgamma.c leaves those fonts alone */
#define GLYPH_W 4                 /* glyph_t (16 bytes, stock's layout; tools/pod.py TEXTGAMMA_PINS): x int16 @0, y int16 @2, w @4, h @6, advance @8, format @0xa (0 = 8-bit alpha), flags @0xb, bitmap pointer @0xc (w * h bytes, stride w) */
#define GLYPH_H 6
#define GLYPH_FORMAT 0xa
#define GLYPH_DATA 0xc
#define LOCALE_COUNTRY 0          /* locale_info_t: country[3] then language[3]: locale_info_reload builds "%s_%s" from +3, +0 (@0x658970) */
#define LOCALE_LANGUAGE 3
#define EVT_LOCALE_CHANGED 0x122  /* locale_info_change dispatches it when the language changes (@0x658a7c) */
#define EVT_THEME_CHANGED 0x14a   /* widget_set_theme dispatches it on the window manager after the font reload (@0x66d4bc) */

/* The Vinyl page (patch/vinyl.c, docs/modules/vinyl.md; tools/vinyl_art.py draws the pictures from the same numbers, test/pod/vinyl.py checks them). PORTRAIT, fullscreen 320 x 480:
 * frame (x, y) is the screen's. Angles are in 1/16 degree, positive clockwise on the screen; sines and cosines are 1/16384. */
#define VN_W 320
#define VN_H 480
#define VN_REC_X 96               /* the record's centre (a pixel corner) and radius */
#define VN_REC_Y 196
#define VN_REC_R 162
#define VN_LAB_R 76               /* the label (the cover, VN_LAB_PX square, its centre VN_LAB_R, VN_LAB_R) and the radius it is drawn in (the white rim covers its edge) */
#define VN_LAB_PX 152
#define VN_LAB_IN 77
#define VN_PIV_X 276              /* the tonearm's pivot (a pixel corner) */
#define VN_PIV_Y 70
#define VN_ARM_W 353              /* vinyl_arm and vinyl_armsh: the arm pointing +x, the pivot at (VN_ARM_PX, VN_ARM_PY) of the picture (a pixel corner) */
#define VN_ARM_H 59
#define VN_ARM_PX 73
#define VN_ARM_PY 22
#define VN_SH_DX 5                /* the arm's shadow lies this far right and down */
#define VN_SH_DY 7
#define VN_PARK 1391              /* the arm's turn parked straight down beside the record (paused, stopped); on the record it is vn_groove (VN_GROOVE_N + 1 points) */
#define VN_GROOVE_N 32
#define VN_LID_X 16               /* vinyl_lid (VN_LID_PX square): the step, gloss, white rim and spindle over the turning label */
#define VN_LID_Y 116
#define VN_LID_PX 160
#define VN_RB_X0 0                /* vinyl_rec (RGB the bare plinth, A the record map) at (X0, Y0), W x H: the record's box */
#define VN_RB_Y0 34
#define VN_RB_W 258
#define VN_RB_H 324
#define VN_RECS 2                 /* the record colours: Black, Cover (tinted from the playing track's cover) */
#define VN_REC_COVER 1
#define VN_THEMES 2               /* the plinth themes: Graphite, Snow (tools/vinyl_art.py THEME_NAMES) */
#define VN_REC_K 15               /* the black record's grey at its rim (tools/vinyl_art.py REC_EDGE_K) */
#define VN_GRAIN 6                /* Graphite's film grain amplitude (tools/vinyl_art.py GRAIN; Snow has none), added to the base where vinyl_grain says */
#define VN_CAP_X 262              /* vinyl_cap (VN_CAP_PX square): the gimbal cap over the pivot */
#define VN_CAP_Y 56
#define VN_CAP_PX 32
#define VN_BAND_Y0 420            /* the key band (rows y0 .. y1 exclusive) and each key's columns: previous, play / pause, next; the band below VN_BAND_Y0 is never composed */
#define VN_BAND_Y1 478
#define VN_PREV_X0 170
#define VN_PLAY_X0 223
#define VN_NEXT_X0 269
#define VN_NEXT_X1 318
#define VN_KEYS_W 286             /* vinyl_keys: the play key's four looks at x 0, 46, 92, 138 (play, pause, + pressed), previous pressed at VN_CELL_PREV, next pressed at VN_CELL_NEXT */
#define VN_CELL_PREV 184
#define VN_CELL_NEXT 237
#define VN_CLOSE_X1 52            /* the close chevron's touch area (0, 0) .. (x1, y1) exclusive */
#define VN_CLOSE_Y1 44
#define VN_TAP_PX 14              /* a touch that travels less than this is a tap (the record) */
#define VN_SPEED 3200             /* 33 1/3 rpm: 200 degrees a second */
#define VN_SPINUP_MS 700          /* the label reaches its speed in this, and stops in VN_SPINDOWN_MS */
#define VN_SPINDOWN_MS 2000
#define VN_DT_MAX 100             /* a late tick moves things as this would: stock's pause blocks the loop 150 ms (play_pause_music usleep 0x4e4460), so motion resumes, not leaps */
#define VN_ARM_STEP 4             /* the arm is redrawn when its turn changes by this (1/4 degree); a change over VN_ARM_SNAP swings there, eased over VN_SWING_MS + 1 ms a 1/16 degree */
#define VN_ARM_SNAP 16
#define VN_SWING_MS 300
#define VN_PLAY_MS 50             /* the page timer while the label turns or the arm swings, and at rest */
#define VN_IDLE_MS 500
#define VN_FIRST_MS 50
#define VN_COVER_MS 500           /* after a track change the /tmp cover is looked at again every VN_COVER_MS, VN_SETTLE times */
#define VN_SETTLE 8
/* ---------------------------------------------------------------------------
 * Light Mode (patch/palette.c, docs/modules/accent.md; the numbers are q2-pod's, tools/palette.py reads them from here). A neutral colour (its channels within LIGHT_SPREAD of each other)
 * flips per channel, black to LIGHT_PAPER and white to LIGHT_INK, alpha kept; any other hue stays. A theme image with no pixel more than LIGHT_CHROMA saturated flips too when it is
 * mostly glyph: under 1/LIGHT_SURFACE of its area opaque and darker than LIGHT_GLYPH, so a grey or dark disc keeps its white glyph.
 * STYLE_*: the hook sites, stock's style_get_color (0x659fcc: the PIC prologue is the hook; it calls style_get_gradient with a bal at 0x65a048 that returns to
 * STYLE_COLOR_GRADIENT_RET and stays unmapped, its colour being mapped once by the colour hook), style_get_gradient (0x659f9c, a leaf without prologue) and image_manager_add (0x655638).
 */
#define LIGHT_PAPER 0xf4
#define LIGHT_INK 0x16
#define LIGHT_SPREAD 16
#define LIGHT_CHROMA 40
#define LIGHT_GLYPH 0xa0
#define LIGHT_SURFACE 4
#define LIGHT_FROM 7    /* Auto: light from this hour (07:00) ... */
#define LIGHT_UNTIL 19  /* ... to this one (18:59) by the device clock */
#define LIGHT_TICK_MS 60000 /* how often Auto looks at the clock: one timer, only while Auto is chosen */
/* The accent (patch/palette.c, tools/palette.py reads these): colours as 0xRRGGBB (the C swaps them into color_t words). ACC_* are the picker's accents, in index order after Neutral (0);
 * ROLE_* the built theme's unique colours of the roles an accent changes (the hooks see a colour, not the style it came from): a pressed row (also LIST_PRESS) turns
 * mix(black, accent, ACC_TINT %), the Now Playing progress fill (alpha kept) the accent. A test over the built tree proves no other style or payload colour is one. ACC_CARD is the settings
 * card colour (the pressed card piece becomes mix(ACC_CARD, accent, ACC_TINT %)); the image rules' end points: a fill image's pixels run from ACC_TRACK_R (the #333333 track) to ACC_FILL_R
 * (#EEEEEC fill), a switch's from ACC_FILL_R (track) down to ACC_KNOB_R (#141414 knob, white in an accent). */
#define ACC_COUNT 7
#define ACC_RED 0xff453a
#define ACC_ORANGE 0xff9f0a
#define ACC_GREEN 0x30d158
#define ACC_TEAL 0x40c8e0
#define ACC_PURPLE 0xbf5af2
#define ACC_CHAMPAGNE 0xc8a96a
#define ACC_TINT 22
#define ACC_WASH 12  /* the Tinted background: a dark neutral colour (channels within LIGHT_SPREAD, none above ACC_DARK) takes this percent of the accent */
#define ACC_DARK 0x40
#define ACC_CARD 0x1c1c1e /* the one near-black surface (tools/pod_roles.py SURFACE_RGB): the Settings cards, fields, flat pills, tiles */
#define ACC_TRACK_R 51
#define ACC_FILL_R 238
#define ACC_KNOB_R 20
#define ACC_TILE 0x1c1c1e /* the Podcasts Library tiles' square (the surface, #1C1C1E): stays exactly, the white glyph on it goes to the accent; its red is the lightness scale's low end */
#define TB_CARD_GREY 28 /* the EQ cards' baked grey (patch/tenband.c tb_cpx adds the surface's blue 30 on that exact grey) */
#define ROLE_PRESS_ROW 0x333334
#define ROLE_PROGRESS 0xfffffe
#define ROLE_FILL 0xebebec /* the own progress fills (Home cache pill, Podcasts refresh and Software Update dialogs; tools/pod_ui.py PD_FILL_RGB): #EBEBEB one blue level up, the accent maps it */
#define ROLE_SHEET_PRESS 0xfffffd /* a pressed row of a bottom sheet / floating card (tools/pod_ui.py PL_PRESSED, #FFFFFD10): white at 6 % alpha over glass; an accent makes it the accent at ACC_SHEET_A */
#define ACC_SHEET_A 56 /* alpha of that pressed row under an accent: ACC_TINT (22) percent of 255 */
#define ROLE_PRESS_PILL 0x333335 /* the pressed Play / Shuffle pill (tools/pod_ui.py SG_PILL_PRESS_RGB; one blue level off #333333): mix(ACC_PILL, accent, ACC_TINT %) */
#define ROLE_PRESS_QPILL 0x3a3a3d /* the Queue's Shuffle / Repeat buttons pressed while off (QP_PILL_OFF_DOWN): mix(ACC_QPILL, accent, ACC_TINT %) */
#define ACC_PILL 0x1c1c1e /* the flat pills' rest colour (SG_PILL_RGB, the surface) */
#define ACC_QPILL 0x2c2c2e /* the Queue's off buttons' rest colour (QP_PILL_OFF) */
#define ACC_SHUF 0x2a2a2a /* the album page's Shuffle disc at rest (ah_shuffle); pressed ah_shuffle_down is ACC_SHUF_DOWN_R grey with the white glyph */
#define ACC_SHUF_DOWN_R 68
#define STYLE_COLOR_GRADIENT_RET 0x65a050
#define BITMAP_PREMULTI 16 /* AWTK's BITMAP_FLAG_PREMULTI_ALPHA in bitmap_t's u16 flags @0xc */

/* The "..." card of the pages with a sort order and a grid / list view (patch/viewsort.c, tools/pod_ui.py view_sort_card; the Albums page first): an Apple-style grouped menu in its own glass.
 * Slots 0..VS_SORTS - 1 are the sort rows, then VS_VIEWS view rows (Grid, List), then Search (VS_SEARCH) and Select (VS_SELECT); the card shows Search and Select first, then the view rows, then the sorts: VS_ROWS rows of VS_ROW_H. A tick sits at VS_TICK_X on every
 * row but Search, a glyph (view rows, Search, Select) at VS_LABEL_X, its label at VS_LABEL_X_GLYPH, a sort label at VS_LABEL_X. The ticked sort row's label moves up (VS_LABEL2_Y, VS_LABEL2_H) for the direction line
 * under it (VS_SUB_Y, VS_SUB_H). The width is the widest label or direction line + its x + VS_LABEL_R, VS_CARD_MIN..PL_CARD_MAX, the right edge PL_CARD_RIGHT. */
#define VS_SORTS 4
#define VS_VIEWS 2
#define VS_SEARCH (VS_SORTS + VS_VIEWS) /* slot 6: the optional Search row, the card's first (a glyph, no tick) */
#define VS_SELECT (VS_SEARCH + 1) /* slot 7: the optional Select row, second in the card (a check-circle glyph, no tick) */
#define VS_ACT2 (VS_SELECT + 1) /* slot 8: an optional third action row (only the Playlists asset has it: New Playlist, Import, Export, Delete Playlists are slots 6..9), a glyph, no tick */
#define VS_ACT3 (VS_ACT2 + 1) /* slot 9: the fourth */
#define VS_ROWS (VS_ACT3 + 1)
#define VS_ALL_SORTS ((1u << VS_SORTS) - 1)
#define VS_WITH_ACT2 (1u << VS_ACT2) /* the vs_bind mask bits that offer slots 8 and 9 */
#define VS_WITH_ACT3 (1u << VS_ACT3)
#define VS_WITH_SEARCH (1u << VS_SEARCH) /* the vs_bind mask bit that offers the Search row */
#define VS_WITH_SELECT (1u << VS_SELECT) /* the vs_bind mask bit that offers the Select row */
#define VS_WITH_VIEWS (((1u << VS_VIEWS) - 1) << VS_SORTS) /* the vs_bind mask bits that offer the two view rows (Grid, List; the Artists page's Show group Artists, Album Artists) */
#define VS_GLASS_FMT "vs_glass%d" /* the glass of the card, one picture per row count (tools/mod_icons.py GLASS_VIEWSORT*: 1, 2, 3, 4, 6 and 7 rows); the asset's own is the seven-row vs_glass7 */
#define VS_ROW_H 50 /* = the bottom sheets' row (docs/modules/ui-rules.md) */
#define VS_TICK_X 14 /* the tick column's left inset */
#define VS_TICK_W 14 /* the tick (sg_tick), centred in the row */
#define VS_GLYPH 20 /* the view rows' and the Search row's glyph */
#define VS_GLYPH_X 38 /* the glyph: VS_TICK_X + VS_TICK_W + 10 */
#define VS_LABEL_X 38 /* a sort label: the glyph column's x */
#define VS_LABEL_X_GLYPH 66 /* a label after a glyph: VS_GLYPH_X + VS_GLYPH + 8 */
#define VS_LABEL_R 16
#define VS_CARD_MIN 206 /* 220 less the 14 px the glyph labels gained (VS_LABEL_X_GLYPH 80 -> 66) */
#define VS_LABEL2_Y 5
#define VS_LABEL2_H 22
#define VS_SUB_Y 25
#define VS_SUB_H 22

/* The Equalizer page (patch/peq_ui.c, tools/pod_ui.py build_peq_page, docs/modules/peq.md): rows pod_row0 (the switch, pod_switch0), pod_row1 (Graphic EQ)
 * and PQ_ROWS preset rows from pod_row2, each with its label pod_label<i> and, from row 1, the picker check pod_check<i>; a cards page (docs/modules/settings.md). */
#define PQ_FIRST 2                /* the first preset row */
#define PQ_ROWS 64                /* preset rows: the files of /mnt/mmc/EQ the page lists, sorted by name (the Equalizer page; the Presets page has PQ_ROWS per section) */
/* The preset page (patch/peqpage.c, tools/pod_ui.py build_peqpage_page / cards_graph, tools/pod_settings.py, docs/modules/peq.md "Preset page"): a cards page; pod_graph is the graph card, a transparent
 * view GRAPH_H = GR_H high whose EVT_BEFORE_PAINT blits a GR_W x GR_H bitmap (the card baked in: #1C1C1E, GR_CARD_R corners in the alpha, the grid and the curve) at x GR_CARD_X; pod_row0 the preamp row
 * (pod_value0), pod_row1 .. GR_BANDS the band rows (pod_label<i> the frequency, pod_value<i> the gain, pod_sub<i> the grey line). The plot is GR_PW columns from card x GR_PX0, GR_DECADE per decade
 * from 20 Hz to 20 kHz (a column per pixel), GR_PH rows from card y GR_PY0, +R dB at the top and -R at the bottom, R 12, 18 or 24. */
#define GR_W 300
#define GR_H 170
#define GR_CARD_X 10
#define GR_CARD_R 12
#define GR_PX0 36
#define GR_PW 249
#define GR_PY0 9
#define GR_PH 138
#define GR_DECADE 83
#define GR_BANDS 30
/* The 10-Band editor's slider card (patch/tenband.c, tools/pod_ui.py cards_sliders, docs/modules/peq.md "10-Band EQ"): pod_sliders is a view TB_H high; its EVT_BEFORE_PAINT blits a TB_W x TB_H bitmap (the card #1C1C1E
 * baked in with TB_R corners and the TB_COLS tracks, TB_TRACK_W wide) at x TB_CARD_X, then a thumb TB_THUMB_W x TB_THUMB_H per column, and the white pill behind the value being dragged. Column c is TB_COL_W wide from card x TB_X0 + c * TB_COL_W;
 * the track runs from card y TB_Y0 (+12 dB) down TB_SPAN px (-12 dB: TB_PX_DB px a decibel, so two a half-decibel step); pod_sl_v<c> (value) and pod_sl_f<c> (frequency) are labels over / under the column. */
#define TB_W 300
#define TB_H 170
#define TB_CARD_X 10
#define TB_R 12
#define TB_COLS 10
#define TB_COL_W 29
#define TB_X0 5
#define TB_Y0 40
#define TB_SPAN 96
#define TB_PX_DB 4
#define TB_TRACK_W 4
#define TB_THUMB_W 24
#define TB_THUMB_H 13
#define TB_VAL_Y 10
#define TB_VAL_H 18
#define TB_FREQ_Y 145
#define TB_FREQ_H 18
#define TB_PILL_W 34
#define TB_PILL_H 18
#define TB_LABEL_W 36 /* a value or frequency label: wider than its column (a value like -11.5 at TB_LABEL_PX), centred on it; the labels never take a touch */
#define TB_LABEL_PX 11
/* The band page (patch/peqband.c, tools/pod_ui.py cards_segment / cards_hsliders, docs/modules/peq.md "Preset editing"). pod_seg is a view BD_SEG_ITEM_H high holding the Peak / Low shelf / High shelf control: its EVT_BEFORE_PAINT blits a BD_SEG_W x BD_SEG_H
 * bitmap (the container #1C1C1E, BD_SEG_R corners) at x BD_CARD_X, y BD_SEG_Y, then the selected segment's pill (BD_SEG_PILL_W x BD_SEG_PILL_H, BD_SEG_PAD in); pod_seg_l<k> are the three labels. pod_hsl is a view BD_HSL_H high: a BD_HSL_W x BD_HSL_H card bitmap with the
 * BD_ROWS rows' tracks (BD_TRACK_W px from card x BD_TRACK_X, BD_TRACK_H thick, centred BD_TRACK_Y into each BD_ROW_H row) baked in, a white fill from the left end to the thumb and a BD_THUMB round thumb; pod_hs_n<r> (name) and pod_hs_v<r> (value) are the row's labels in its top BD_TEXT_H px,
 * where a tap types the value. The graph card of the preset page is above them; BD_RING is the ring that marks the band on its curve. */
#define BD_CARD_X 10
#define BD_SEG_ITEM_H 58
#define BD_SEG_Y 10
#define BD_SEG_W 300
#define BD_SEG_H 40
#define BD_SEG_R 10
#define BD_SEG_PAD 3
#define BD_SEG_PILL_W 94
#define BD_SEG_PILL_H 34
#define BD_HSL_W 300
#define BD_HSL_H 150
#define BD_HSL_R 12
#define BD_ROWS 3
#define BD_ROW_H 50
#define BD_TRACK_X 14
#define BD_TRACK_W 272
#define BD_TRACK_Y 38
#define BD_TRACK_H 4
#define BD_THUMB 22
#define BD_TEXT_H 28
#define BD_NAME_X 14
#define BD_NAME_W 150
#define BD_VAL_W 112
#define BD_LABEL_Y 6
#define BD_LABEL_H 22
#define BD_RING 16
/* The band page's number keypad sheet (patch/peqband.c, tools/pod_ui.py band_keypad): the value field is BK_FIELD_W x BK_FIELD_H at BK_FIELD_X, BK_FIELD_Y of the sheet; the payload places bk_unit (BK_UNIT_H high), bk_caret (BK_CARET_W x BK_CARET_H) and
 * bk_val (BK_VAL_H high, right aligned) by the unit's width, BK_PAD in from the field's right edge, BK_CARET_GAP between the number and the unit. */
#define BK_FIELD_X 10
#define BK_FIELD_Y 80
#define BK_FIELD_W 300
#define BK_FIELD_H 48
#define BK_PAD 14
#define BK_VAL_H 44
#define BK_CARET_W 2
#define BK_CARET_H 34
#define BK_CARET_GAP 4
