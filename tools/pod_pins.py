"""Stock-firmware pin data for tools/pod.py: addresses, hook sites, prologues and the *_PINS tables.

A pin is (address, stock word, what it proves): the word the stock demo binary holds at that address,
which a hook or a payload assumption depends on. pod.py checks every table against the stock image before it
patches anything (check_pins); a different stock build fails there. pod.py imports this module with
`from pod_pins import *`, so pod.X_PINS and the address constants keep their names.
"""

# The timed cover page (patch/bigcover.c, docs/modules/bigcover.md, payload hook 23): bigcover_page_init, built by the navigator's page-init dispatcher whenever the page opens (Now Playing's
# 500 ms timer after ~10 s is the only opener). m1plus_bigcover_init runs the stock init, then gives the page a 320 px cover of its own.
VOLKEYS_PINS = (   # (address, stock word, what it proves): the hardware volume keys patch/coverflow.c on_volkey takes on its own page (docs/modules/coverflow.md "Volume buttons")
    (0x670974, 0x2403010f, 'widget_on_keydown: ordinary KEY_DOWN is 0x10f'),
    (0x5ffaf8, 0x2405010f, 'short key injection: key_event_init uses KEY_DOWN 0x10f'),
    (0x6a497c, 0x24050110, 'held-key timer: key_event_init uses KEY_LONG_PRESS 0x110'),
    (0x534fbc, 0x24050113, 'home_page_init: widget_on(wm, 0x113 EVT_KEY_UP, on_wm_keyup_fun)'), (0x534fd8, 0x24050110, 'home_page_init: widget_on(wm, 0x110 KEY_LONG_PRESS, on_wm_keylong_fun)'),
    (0x4cd9f8, 0x8f82ab4c, 'on_wm_keyup_fun: lw v0, GOT ROTATEMODE (0xa05a9c)'), (0x4cda04, 0x14620007, 'on_wm_keyup_fun: ROTATEMODE != 1 skips the swap'),
    (0x4cda0c, 0x8ca20018, 'on_wm_keyup_fun: the key code is the event field 0x18'), (0x4cdaf0, 0x240300dc, 'on_wm_keyup_fun: 0xdc (volume up)'),
    (0x4cdaf8, 0x240500dd, 'on_wm_keyup_fun: 0xdd (volume down)'), (0x4cdb00, 0x240200dd, 'on_wm_keyup_fun: 0xdc becomes 0xdd under ROTATEMODE'),
    (0x47e340, 0x8f82ab4c, 'volume dialog handler 0x47e330: reads ROTATEMODE the same way'), (0x47e3c8, 0x2402000b, 'volume dialog handler: returns RET_STOP (0xb) after stepping the volume'),
    (0x47e494, 0x24050113, 'dialog_volume_dialog_init: widget_on(window, 0x113, handler 0x47e330)'),
)
BIGCOVER_PINS = (   # (address, stock word, what it proves)
    (0x529a30, 0x10800046, 'bigcover_page_init: beqz a0 (the trampoline resumes here)'),
    (0x4d10c8, 0x0320f809, 'page-init dispatcher: jalr strcmp(name, "bigcover_page")'), (0x4d10cc, 0x24a59f50, 'its delay slot: a1 = "bigcover_page"'),
    (0x4d10d8, 0x8f99b5b8, 'page-init dispatcher: lw t9, GOT bigcover_page_init'), (0x4d10e0, 0x0320f809, 'page-init dispatcher: jalr bigcover_page_init(window, ctx)'),
)
# The idle view (patch/bigcover.c bc_timed_open, docs/modules/bigcover.md "Idle view", payload hook 24): the timed open's `jalr navigator_to("bigcover_page")` in Now Playing's page timer callback
# 0x53cf48 becomes `jal bc_timed_open`; the delay slot still loads the name, and everything round it is stock's: the Cover mode byte test, the playing_page window test, the countdown
# (0x97ccd0: decremented before the call, reset to 20 after it). The Settings row's other stock side is the Cover mode row's handler (on_playsetback_onclick 0x4a0098), whose toggle
# idle_cover_mode repeats: [SYSSET] COVERMODE saved with write_int_config, the byte 0xa05aa5 stored.
IDLE_SITE = 0x53d0ec
IDLE_PINS = (   # (address, stock word, what it proves)
    (0x53cf48, 0x3c1c004c, 'the timer callback 0x53cf48: PIC prologue (lui gp)'), (0x53cf4c, 0x279c6f88, 'the timer callback: addiu gp'), (0x53cf50, 0x0399e021, 'the timer callback: addu gp, gp, t9'),
    (0x53d008, 0x8f82ae50, 'the timer callback: lw v0, GOT 0xa05aa5 (Cover mode)'), (0x53d00c, 0x90420000, 'the timer callback: lbu v0, (v0)'), (0x53d010, 0x1040003c, 'the timer callback: beqz v0 (Cover mode off: no timed open)'),
    (0x53d0bc, 0x8f85a708, 'the timer callback: lw a1, GOT (the string page)'), (0x53d0c4, 0x0320f809, 'the timer callback: jalr strcmp(top window name, "playing_page")'),
    (0x53d0c8, 0x24a55b14, 'its delay slot: a1 = "playing_page"'), (0x53d0cc, 0x1440000c, 'bnez v0: the timed open only with Now Playing on top'),
    (0x53d0d4, 0x8e22ccd0, 'the countdown: lw v0, 0x97ccd0'), (0x53d0d8, 0x2442ffff, 'addiu v0, v0, -1'), (0x53d0dc, 0x14400008, 'bnez: not yet'), (0x53d0e0, 0xae22ccd0, 'sw v0, countdown (in the branch delay slot)'),
    (0x53d0e4, 0x8f848020, 'the timed open: lw a0, GOT (the string page)'), (0x53d0e8, 0x8f99a704, 'the timed open: lw t9, GOT navigator_to'),
    (IDLE_SITE, 0x0320f809, 'the timed open: jalr navigator_to'), (0x53d0f0, 0x24849f50, 'its delay slot: a0 = "bigcover_page"'),
    (0x53d0f4, 0x24020014, 'addiu v0, zero, 20: the countdown restarts'), (0x53d0f8, 0x8fbc0010, 'lw gp, 0x10(sp): stock restores $gp after the call'), (0x53d0fc, 0xae22ccd0, 'sw v0, countdown'),
    # Cover mode's own row (on_playsetback_onclick's case, 0x4a0098): the byte is flipped, saved as [SYSSET] COVERMODE with write_int_config and stored; the Settings row does the same and saves first
    (0x4a0098, 0x8f92ae50, 'cover mode row: lw s2, GOT 0xa05aa5'), (0x4a00ac, 0x92440000, 'cover mode row: lbu a0, (s2)'), (0x4a00b0, 0x24c6745c, 'cover mode row: a2 = "COVERMODE"'),
    (0x4a00b4, 0x24a54540, 'cover mode row: a1 = "SYSSET"'), (0x4a00bc, 0x38840001, 'cover mode row: xori a0, a0, 1'), (0x4a00c0, 0x0320f809, 'cover mode row: jalr write_int_config'),
    (0x4a00c4, 0xa2440000, 'cover mode row: sb a0, (s2) in the delay slot (the byte is stored)'),
    (0x744540, 0x53535953, 'the string "SYSS(ET)"'), (0x74745c, 0x45564f43, 'the string "COVE(RMODE)"'), (0x747460, 0x444f4d52, 'the string "(COVE)RMOD(E)"'),
)
LOCKSCREEN_PINS = (   # (address, stock word, what it proves)
    (0x53fd50, 0x10800054, 'screensaver_page_init: beqz a0 (the trampoline resumes here)'),
    # the lock screen switch (Settings > Lock Screen: the stock systemset/screensaver_page's image_switch click handler 0x4aba34 flips the byte screensaver_mode and saves it): the byte, the order
    # (byte first, then the save) and the save's section and key; config_init and into_standby read the byte (it is read whenever the screen goes dark: 0 = the lock screen never opens)
    (0x4abaa4, 0x8f90affc, 'lock switch handler 0x4aba34: lw s0, GOT screensaver_mode (0xa05aa3)'), (0x4abaa8, 0x92020000, 'lock switch handler: lbu v0, (s0): the current state'),
    (0x4ababc, 0xa2000000, 'lock switch handler: sb zero, (s0): off'), (0x4abb24, 0xa2020000, 'lock switch handler: sb v0 (1), (s0): on'),
    (0x4abaf0, 0x24c6878c, 'lock switch handler: a2 = "SCREENSAVER"'), (0x4abaf8, 0x24a54540, 'lock switch handler: a1 = "SYSSET"'), (0x4abaf4, 0x0320f809, 'lock switch handler: jalr write_int_config(state, "SYSSET", "SCREENSAVER")'),
    (0x4e615c, 0x8f83affc, 'config_init: lw v1, GOT screensaver_mode (the saved value, 0 or 1, is read once at boot)'),
    (0x4e779c, 0x8f82affc, 'into_standby: lw v0, GOT screensaver_mode'), (0x4e77a0, 0x90430000, 'into_standby: lbu v1, (v0): 0 = awake_screen instead of the lock screen'),
    # the Wallpaper picker (docs/modules/lockscreen.md "Wallpaper picker"). The picture list: get_screensaver_image 0x4d7524 (stock's wallpaper page calls it first in its init 0x4abe44) fills pdeq_screensaverlist
    # through toolsGetScreenSaverPic(/mnt/mmc/lockscreenimage, 320, 480, 1 MiB, the deque, at most 5), pushes the name screensaver_default in front, and sets an unreadable chosen picture (access R_OK) back to it
    (0x4d7558, 0x2484a960, 'get_screensaver_image: a0 = "/mnt/mmc/lockscreenimage"'), (0x4d7550, 0x24050140, 'get_screensaver_image: a1 = 320'), (0x4d7548, 0x240601e0, 'get_screensaver_image: a2 = 480'),
    (0x4d7540, 0x3c070010, 'get_screensaver_image: a3 = 0x100000 (1 MiB)'), (0x4d7538, 0x24020005, 'get_screensaver_image: v0 = 5'), (0x4d755c, 0xafa20014, 'get_screensaver_image: the limit 5 is the 6th argument'),
    (0x4d7578, 0x2605a97c, 'get_screensaver_image: a1 = "screensaver_default"'), (0x4d7584, 0x0320f809, 'get_screensaver_image: jalr _deque_push_front (the Default entry first)'),
    (0x4d759c, 0x2605a97c, 'get_screensaver_image: strcmp(picture, "screensaver_default")'), (0x4d75b4, 0x24050004, 'get_screensaver_image: access(picture, R_OK)'),
    (0x4abe44, 0x0320f809, 'wallpaper page init: jalr get_screensaver_image, the first thing'),
    # the grid: three columns (x 12, then + 103), y 0 then 143, 90 x 135 (the cell builder 0x4abb3c: scale_auto = draw type 4, a 26 px mark child)
    (0x4abed0, 0x24020087, 'wallpaper page init: h = 135'), (0x4abed4, 0x2407005a, 'wallpaper page init: w = 90'), (0x4abf0c, 0x26520067, 'wallpaper page init: x += 103'), (0x4abf38, 0x2412000c, 'wallpaper page init: x = 12'),
    (0x4abefc, 0x2403008f, 'wallpaper page init: y = 143 after the third'), (0x4abf10, 0x2403000c, 'wallpaper page init: x = 12 after the third'), (0x4abf00, 0x3a220002, 'wallpaper page init: xori v0, s1, 2'),
    (0x4abbd4, 0x24050004, 'cell builder 0x4abb3c: image_set_draw_type(cell, 4)'), (0x4abc48, 0x2402001a, 'cell builder: the mark is 26 px'),
    # the tap handler 0x4ab52c (cell i: a1 = i): nothing to do when it is the chosen one; the old mark off (picture_unselect_style, screensaver_unselect), the new one on (picture_selected_style, screensaver_selected),
    # the global screensaver_picture = the item ("%s", 256), then toolsWriteConfig("/mnt/data/config.ini", "SYSSET", "SCREENSAVERPATH", picture); no refresh flag, no other write
    (0x4ab590, 0x12320084, 'wallpaper tap 0x4ab52c: beq s1, s2: the chosen one again does nothing'), (0x4ab7e0, 0x8f85b008, 'wallpaper tap: the chosen one is found by strcmp(item, screensaver_picture)'),
    (0x4ab608, 0x24a586ec, 'wallpaper tap: picture_unselect_style'), (0x4ab674, 0x24a58704, 'wallpaper tap: screensaver_unselect'), (0x4ab6dc, 0x24a5871c, 'wallpaper tap: picture_selected_style'), (0x4ab744, 0x24a58734, 'wallpaper tap: screensaver_selected'),
    (0x4ab770, 0x8f84b008, 'wallpaper tap: snprintf(screensaver_picture, 256, "%s", item)'), (0x4ab778, 0x24c61158, 'wallpaper tap: a2 = "%s"'),
    (0x4ab78c, 0x8f99b00c, 'wallpaper tap: lw t9, GOT toolsWriteConfig'), (0x4ab790, 0x24c6874c, 'wallpaper tap: key "SCREENSAVERPATH"'), (0x4ab798, 0x24a54540, 'wallpaper tap: section "SYSSET"'),
    (0x4ab7a0, 0x24844924, 'wallpaper tap: file "/mnt/data/config.ini"'), (0x4ab79c, 0x0320f809, 'wallpaper tap: jalr toolsWriteConfig'),
    # who reads the choice: config_init (boot: the saved path if readable, else the default) and the lock screen's page visitor 0x53f1bc (each time the lock screen is built: access R_OK, then "file://%s"), both of the global
    (0x4e61c4, 0x8f84b008, 'config_init: lw a0, GOT screensaver_picture (memset, then toolsReadConfig SCREENSAVERPATH into a buffer, copied when readable)'),
    (0x53f228, 0x8f84b008, 'lock screen visitor: strcmp(screensaver_picture, "screensaver_default")'), (0x53f230, 0x2625a97c, 'lock screen visitor: a1 = "screensaver_default"'),
    (0x53f258, 0x24050004, 'lock screen visitor: access(screensaver_picture, R_OK)'), (0x53f29c, 0x24c642cc, 'lock screen visitor: "file://%s"'),
    # Show Time (docs/modules/lockscreen.md "Show Time"): stock's img_timeswitch click handler 0x4ab984 stores the byte screensaver_timeshow (0xa05aa2) xor 1 in the delay slot of write_int_config(new, "SYSSET",
    # "SSAVERTIMESHOW"), so the byte is written first and then the save; config_init loads the key once at boot (atoi, 0 or 1: anything above 1 becomes 0) and the lock screen's visitor shows view_timeinfo from the byte
    (0x4ab9c8, 0x8f91b000, 'show time handler 0x4ab984: lw s1, GOT screensaver_timeshow (0xa05aa2)'), (0x4ab9d8, 0x92240000, 'show time handler: lbu a0, (s1): the current state'),
    (0x4ab9e4, 0x38840001, 'show time handler: xori a0, a0, 1: the new state'), (0x4ab9dc, 0x24c6877c, 'show time handler: a2 = "SSAVERTIMESHOW"'), (0x4ab9e0, 0x24a54540, 'show time handler: a1 = "SYSSET"'),
    (0x4ab9e8, 0x0320f809, 'show time handler: jalr write_int_config(new, "SYSSET", "SSAVERTIMESHOW")'), (0x4ab9ec, 0xa2240000, 'show time handler: sb a0, (s1) in the delay slot: the byte first, then the save'),
    (0x4e6190, 0x24c6877c, 'config_init: toolsReadConfig(.., "SYSSET", "SSAVERTIMESHOW")'), (0x4e61ac, 0x2c430002, 'config_init: sltiu v1, v0, 2'), (0x4e61b0, 0x0003100a, 'config_init: movz v0, zero, v1: above 1 is 0'),
    (0x4e61b8, 0x8f83b000, 'config_init: lw v1, GOT screensaver_timeshow'),
    # Screen Timeout (Settings > Display, patch/display.c disp_light_set; docs/modules/display.md): stock's systemset/lighttime_page. Each of its five rows has a click handler
    # (0x4a8708 row 1 = index 0 .. 0x4a8578 row 5 = index 4) that does nothing when the index is the word backlighttime_mode already, else calls the shared 0x4a8410 (the row images, then the word
    # stored in the delay-slot position before write_int_config(index, "SYSSET", "LIGHTTIME")) and then reset_poweroptions_timer(0, 0, 1), which sets the screen's countdown from the new word.
    (0x4a84b8, 0x8f82afb8, 'backlight time 0x4a8410: lw v0, GOT backlighttime_mode (0xa05a7c)'), (0x4a84bc, 0x8c520000, 'backlight time: lw s2, (v0): the current index'),
    (0x4a84c0, 0x12500023, 'backlight time: beq s2, s0: the same index saves nothing'),
    (0x4a8540, 0x24c68108, 'backlight time: a2 = "LIGHTTIME"'), (0x4a8544, 0xae700000, 'backlight time: sw s0, (s3): the word first'),
    (0x4a8548, 0x0320f809, 'backlight time: jalr write_int_config(index, "SYSSET", "LIGHTTIME")'), (0x4a854c, 0x24a54540, 'backlight time: a1 = "SYSSET"'),
    (0x4a85b4, 0x24060001, 'backlight time row handler 0x4a8578: a2 = 1 (the screen countdown)'), (0x4a85bc, 0x00002825, 'backlight time row handler: a1 = 0'),
    (0x4a85c4, 0x0320f809, 'backlight time row handler: jalr reset_poweroptions_timer'), (0x4a85c8, 0x00002025, 'backlight time row handler: a0 = 0'),
    (0x4e60d4, 0x24c68108, 'config_init: toolsReadConfig(.., "SYSSET", "LIGHTTIME")'), (0x4e60f0, 0x2c430005, 'config_init: sltiu v1, v0, 5: the saved index is 0 .. 4'),
    # Brightness (Settings > Display, patch/display.c disp_opened): stock's systemset/brightness_page binds two handlers to slider_brightness with the window as their context: 0x4a4744 on EVT_VALUE_CHANGING (0x11d: the
    # word lightness, backlight_changeflag 1, the refresh 0x4a4450, reset_poweroptions_timer(1, 1, 1)) and 0x4a4678 on EVT_VALUE_CHANGED (0x11c: the flag 0, the word, toolSetBackLight(value + 1), [SYSSET] LIGHTNESS,
    # the refresh, the timers). Both read the slider's value from the event's target and take 0 .. 100 only; the refresh looks up label_brightness and slider_brightness in the window and does nothing without both.
    # Our page binds the same two handlers to its own slider of that name and calls the refresh; none of this is repeated in the payload.
    (0x4a4450, 0x3c1c0056, 'brightness refresh 0x4a4450: prologue'), (0x4a4678, 0x3c1c0056, 'brightness changed handler 0x4a4678: prologue'), (0x4a4744, 0x3c1c0056, 'brightness changing handler 0x4a4744: prologue'),
    (0x4a43ac, 0x2405011d, 'brightness page: widget_on(slider, 0x11d, ..)'), (0x4a43bc, 0x24c64744, '... the changing handler 0x4a4744'),
    (0x4a43c0, 0x2405011c, 'brightness page: widget_on(slider, 0x11c, ..)'), (0x4a43d0, 0x24c64678, '... the changed handler 0x4a4678'),
    (0x4a46b8, 0x2c430065, 'brightness changed handler: sltiu v1, v0, 0x65: 0 .. 100'), (0x4a4780, 0x2c430065, 'brightness changing handler: sltiu v1, v0, 0x65'),
    # LED Light and Follow Screen (patch/display.c disp_led_set, disp_follow_toggle): stock's systemset/atmosphereled_page. The byte atmosphereled_mode is 0 off, 1 green, 2 blue. The navbar switch 0x4a1c30 stores 0
    # (from non-zero) or 1 (from 0); img_orange 0x4a1e14 stores 1 and img_blue 0x4a1d8c stores 2 unless it is the mode already; each then saves [SYSSET] ATMOSPHERELEDMODE and calls reset_atmosphereled_rgb.
    # Follow Screen 0x4a1940 stores the byte ledfollowscreen_flag xor 1 (as 0 / 1) in the delay slot of write_int_config(new, "SYSSET", "LEDFOLLOWSCREEN") and calls nothing else. config_init keeps 0 .. 2 and 0 .. 1.
    (0x4a1ca8, 0x82220000, 'led switch 0x4a1c30: lb v0, (s1): atmosphereled_mode'), (0x4a1cbc, 0xa2200000, 'led switch: sb zero, (s1): off'), (0x4a1d60, 0xa2220000, 'led switch: sb v0 (1), (s1): on is green'),
    (0x4a1d04, 0x24c67820, 'led switch: a2 = "ATMOSPHERELEDMODE"'), (0x4a1d18, 0x0320f809, 'led switch: jalr reset_atmosphereled_rgb after the save'),
    (0x4a1db8, 0x10830011, 'led blue 0x4a1d8c: beq a0, v1 (2): the same mode does nothing'), (0x4a1dd0, 0xa0430000, 'led blue: sb v1 (2), (v0) before the save'),
    (0x4a1e40, 0x10830011, 'led orange 0x4a1e14: beq a0, v1 (1): the same mode does nothing'), (0x4a1e58, 0xa0430000, 'led orange: sb v1 (1), (v0) before the save'),
    (0x4a1964, 0x24c677ec, 'follow screen 0x4a1940: a2 = "LEDFOLLOWSCREEN"'), (0x4a197c, 0x38420001, 'follow screen: xori v0, v0, 1'), (0x4a1980, 0x0002202b, 'follow screen: sltu a0, zero, v0: the new state, 0 or 1'),
    (0x4a1984, 0x0320f809, 'follow screen: jalr write_int_config'), (0x4a1988, 0xa0640000, 'follow screen: sb a0, (v1) in the delay slot: the byte first'),
    (0x4e6718, 0x2c440003, 'config_init: sltiu a0, v0, 3: the saved lamp mode is 0 .. 2'), (0x4e6b9c, 0x3c1c0052, 'reset_atmosphereled_rgb: prologue'),
    (0x53f32c, 0x8f82b000, 'lock screen visitor: lw v0, GOT screensaver_timeshow'), (0x53f330, 0x90420000, 'lock screen visitor: lbu v0, (v0): view_timeinfo is shown (and enabled) from the byte'), (0x53f334, 0x1040000b, 'lock screen visitor: beqz v0: hidden'),
)
# The Display page's Lock Screen row (docs/modules/lockscreen.md "The Display row"): systemset_display_page_init (0x4a5f58) installs the row click handler 0x4a5c10 (atoi of the row's name: 0 brightness, 1 light time,
# 2 lock screen, 3 atmosphere LED; each a navigator_to). The case for 2 (lw a0, GOT; b 0x4a5c88; addiu a0, "systemset/screensaver_page", reached by the beq v0, 2 at 0x4a5c38) is that string's only caller. Its first two
# words become `j pod_lock_site; nop`: the stub calls lk_redirect (our Lock Screen page; 0 on the kill switch or a page that will not open) and then either resumes at the handler's epilogue (0x4a5c94) or does stock's two
# words and jumps to the shared navigator_to call (0x4a5c88). The only other reference to the string, 0x4d14a8, is the navigator's page-init dispatcher (a strcmp), not a caller. Not reachable at boot (a list click).
LOCKROW = 0x4a5ca8
LOCKROW_NAV, LOCKROW_DONE = 0x4a5c88, 0x4a5c94
LOCKROW_PINS = (   # (address, stock word, what it proves)
    (0x4a5c1c, 0x27bdffe0, 'Display row handler 0x4a5c10: addiu sp, sp, -0x20'), (0x4a5c28, 0xafbf001c, 'its sw ra, 0x1c(sp)'), (0x4a5c38, 0x1043001b, 'its `beq v0, v1 (2)` to the lock screen case 0x4a5ca8'),
    (LOCKROW, 0x8f84a708, 'Display row, case 2: lw a0, GOT 0x740000'), (LOCKROW + 4, 0x1000fff6, 'its `b 0x4a5c88` (the shared navigator_to call)'), (LOCKROW + 8, 0x24847d24, 'its delay slot: a0 = "systemset/screensaver_page"'),
    (LOCKROW_NAV, 0x8f99a704, 'Display row: lw t9, GOT navigator_to'), (LOCKROW_NAV + 4, 0x0320f809, 'its jalr navigator_to'), (LOCKROW_DONE, 0x1000fff2, 'Display row epilogue: b 0x4a5c60'), (LOCKROW_DONE + 4, 0x8fbf001c, 'its delay slot: lw ra, 0x1c(sp)'),
    (0x4a5c60, 0x00001025, 'Display row: move v0, zero'), (0x4a5c68, 0x27bd0020, 'Display row: addiu sp, sp, 0x20'), (0x4a5f58, 0x26525c10, 'display page init: the row handler is 0x4a5c10 (its one reference)'),
)
# Settings > System > Buttons & Power (patch/keyspower.c, docs/modules/keyspower.md): the four controls of stock's systemset/keylock_page, the sysset list's row 7 and systemset/powermanager_page, as their click handlers
# do them. Button Lock: the switch 0x4a7a04 xors the byte keylock_flag and saves LOCKFLAG after the refresh 0x4a770c (which saves nothing for the unchanged mode); a choice 0x4a7a7c / 0x4a7ab8 / 0x4a7af4 calls the
# refresh with 1 / 2 / 3, which stores the word keylock_mode (the store sits in the delay slot of the save) and saves LOCKMODE only when the word differs. Which keys the mode locks is read off the gates: the volume
# keys (0x47e3a4, 0x4cdc20) pass only for mode 2, the play / prev / next keys (0x4cda60) only for mode 1. Tap to Wake: the case of the shared sysset click handler 0x4ad930 saves DOUBLEWAKE with the byte xor 1 stored in
# the call's delay slot. Auto-Standby 0x4a97c4 and Auto-Shutdown 0x4a966c: the byte, the word, the saves and reset_poweroptions_timer(1, 1, 0) as pinned; a duration choice (0x4a9cb4 .. 0x4a9b88) returns for the
# same word, else the refresh 0x4a92a4 stores the word before its save, then reset_poweroptions_timer(0, 1, 0). config_init clamps every value to its range.
KEYSPOWER_PINS = (   # (address, stock word, what it proves)
    (0x4a7a24, 0x8f90a94c, 'lock switch 0x4a7a04: lw s0, GOT keylock_flag'), (0x4a7a34, 0x38420001, 'lock switch: xori v0, v0, 1'), (0x4a7a38, 0xa2020000, 'lock switch: sb v0, (s0): the byte first'),
    (0x4a7a40, 0x0411ff32, 'lock switch: bal refresh 0x4a770c (the word as it is: no mode save)'), (0x4a7a5c, 0x24c64534, 'lock switch: a2 = "LOCKFLAG"'), (0x4a7a60, 0x0320f809, 'lock switch: jalr write_int_config after the refresh'),
    (0x4a7aa0, 0x0411ff1a, 'lock choice 0x4a7a7c: bal refresh'), (0x4a7aa4, 0x24050001, 'lock choice 1: a1 = 1 (volume keys)'), (0x4a7adc, 0x0411ff0b, 'lock choice 0x4a7ab8: bal refresh'),
    (0x4a7ae0, 0x24050002, 'lock choice 2: a1 = 2 (the other keys)'), (0x4a7b18, 0x0411fefc, 'lock choice 0x4a7af4: bal refresh'), (0x4a7b1c, 0x24050003, 'lock choice 3: a1 = 3 (both)'),
    (0x4a7900, 0x12330023, 'lock refresh: beq s1, s3: the same mode saves nothing'), (0x4a7980, 0x24c67fa8, 'lock refresh: a2 = "LOCKMODE"'), (0x4a7984, 0xae910000, 'lock refresh: sw s1, (s4): the word in the save\'s call slot'),
    (0x4a7988, 0x0320f809, 'lock refresh: jalr write_int_config'),
    (0x47e3a8, 0x24030002, 'volume key gate 0x47e38c: mode 2 lets the keys through'), (0x47e3b0, 0x14a30006, 'volume key gate: bne mode, 2: locked otherwise'),
    (0x4cda68, 0x24030001, 'play key gate 0x4cda44: mode 1 lets the keys through'), (0x4cda6c, 0x1483005e, 'play key gate: bne mode, 1: locked otherwise'),
    (0x4cdc28, 0x24020002, 'volume key gate 0x4cdc04: mode 2'), (0x4cdc2c, 0x1462ff98, 'volume key gate: bne mode, 2'),
    (0x4e6318, 0x2c430002, 'config_init: LOCKFLAG sltiu v1, v0, 2'), (0x4e6338, 0xa0620000, 'config_init: LOCKFLAG stored as a byte'),
    (0x4e6378, 0x2443ffff, 'config_init: LOCKMODE addiu v1, v0, -1'), (0x4e6380, 0x2c630003, 'config_init: LOCKMODE sltiu v1, v1, 3: 1 .. 3 kept'), (0x4e6384, 0x02a3100a, 'config_init: movz v0, s5 (1): else 1'),
    (0x4ad930, 0x8f92b06c, 'tap to wake case 0x4ad930: lw s2, GOT doublewake_flag'), (0x4ad944, 0x92440000, 'tap to wake: lbu a0, (s2)'), (0x4ad948, 0x24c689b4, 'tap to wake: a2 = "DOUBLEWAKE"'),
    (0x4ad954, 0x38840001, 'tap to wake: xori a0, a0, 1'), (0x4ad958, 0x0320f809, 'tap to wake: jalr write_int_config'), (0x4ad95c, 0xa2440000, 'tap to wake: sb a0, (s2) in the delay slot: the byte first'),
    (0x4e62b8, 0x2c430002, 'config_init: DOUBLEWAKE sltiu v1, v0, 2'), (0x4e62d0, 0x30420001, 'config_init: DOUBLEWAKE andi v0, v0, 1'), (0x4e62d8, 0xa0620000, 'config_init: DOUBLEWAKE stored as a byte'),
    (0x4a9794, 0x8f82afd8, 'shutdown switch 0x4a966c, from off: lw v0, GOT standbyflag'), (0x4a9798, 0x90430000, 'shutdown switch: lbu v1, (v0)'), (0x4a979c, 0x1060ffe0, 'shutdown switch: beqz v1: a standby that is off is not saved'),
    (0x4a97b0, 0xa0400000, 'shutdown switch: sb zero: Auto-Standby off'), (0x4a97b4, 0x0320f809, 'shutdown switch: jalr write_int_config'), (0x4a97b8, 0x24c68374, 'shutdown switch: a2 = "STANDBYMODE"'),
    (0x4a978c, 0x24020001, 'shutdown switch, from off: v0 = 1'), (0x4a9790, 0xae020000, 'shutdown switch: sw v0, (s0): the word 1 before the standby save'),
    (0x4a971c, 0xae000000, 'shutdown switch, from on: sw zero, (s0): the word 0'), (0x4a9724, 0x26454540, 'shutdown switch: a1 = "SYSSET"'), (0x4a972c, 0x8e040000, 'shutdown switch: a0 = the word'),
    (0x4a975c, 0x8f99a874, 'shutdown switch: lw t9, GOT reset_poweroptions_timer'), (0x4a9760, 0x0320f809, 'shutdown switch: jalr reset_poweroptions_timer'), (0x4a9764, 0x24040001, 'shutdown switch: a0 = 1 (a1 = 1, a2 = 0)'),
    (0x4a97f8, 0x8f90afd8, 'standby switch 0x4a97c4: lw s0, GOT standbyflag'), (0x4a9800, 0x92020000, 'standby switch: lbu v0, (s0)'), (0x4a9804, 0x1040001e, 'standby switch: beqz v0: from off'),
    (0x4a980c, 0xa2000000, 'standby switch, from on: sb zero, (s0)'), (0x4a981c, 0x92040000, 'standby switch: a0 = the byte, saved as STANDBYMODE'),
    (0x4a9880, 0x8e920000, 'standby switch, from off: lw s2, (s4): the Auto-Shutdown word'), (0x4a9888, 0x1a40ffe1, 'standby switch: blez s2: no shutdown to clear'), (0x4a988c, 0xa2020000, 'standby switch: sb v0 (1), (s0) in the delay slot'),
    (0x4a9910, 0xae800000, 'standby switch: sw zero, (s4): the word 0, then the save of SAVEPOWERMODE (0x4a9918)'), (0x4a9918, 0x24c68364, 'standby switch: a2 = "SAVEPOWERMODE"'),
    (0x4a9848, 0x24050001, 'standby switch: a1 = 1'), (0x4a984c, 0x8f99a874, 'standby switch: lw t9, GOT reset_poweroptions_timer'), (0x4a9854, 0x24040001, 'standby switch: a0 = 1 (a1 = 1, a2 = 0)'),
    (0x4a95a8, 0xaed10000, 'duration refresh 0x4a92a4: sw s1, (s6): the word before the save'), (0x4a9520, 0x8ed30000, 'duration refresh: lw s3, (s6): the old word'), (0x4a9524, 0x12710024, 'duration refresh: beq s3, s1: the same word saves nothing'),
    (0x4a95a4, 0x24c68364, 'duration refresh: a2 = "SAVEPOWERMODE"'),
    (0x4a9ba8, 0x24020004, 'duration choice 0x4a9b88: v0 = 4 (10min)'), (0x4a9bac, 0x1062000c, 'duration choice: the same word returns'), (0x4a9bc0, 0x24050004, 'duration choice: refresh(win, 4)'),
    (0x4a9bcc, 0x24050001, 'duration choice 10min: a1 = 1'), (0x4a9bd4, 0x0320f809, 'duration choice: jalr reset_poweroptions_timer'), (0x4a9bd8, 0x00002025, 'duration choice: a0 = 0 (a1 = 1, a2 = 0)'),
    (0x4a9cd4, 0x24020001, 'duration choice 0x4a9cb4: v0 = 1 (1min)'), (0x4a9cec, 0x24050001, 'duration choice: refresh(win, 1)'), (0x4a9cf8, 0x24050001, 'duration choice 1min: a1 = 1'),
    (0x4a9c70, 0x24020002, 'duration choice 0x4a9c50: v0 = 2 (3min)'), (0x4a9c0c, 0x24020003, 'duration choice 0x4a9bec: v0 = 3 (5min)'),
    (0x4e5fd4, 0x2c430002, 'config_init: STANDBYMODE sltiu v1, v0, 2'), (0x4e5fec, 0x30420001, 'config_init: STANDBYMODE andi v0, v0, 1'), (0x4e6034, 0x2c430005, 'config_init: SAVEPOWERMODE sltiu v1, v0, 5: 0 .. 4'),
)
# Playback settings (patch/playset.c, docs/modules/playset.md): the rows of stock's playset/playset_page and its sub-pages as their click handlers do them. The list's click handler 0x49ffec reads the row number
# from the item's name (atoi), maps it through the table 0x97c7d0 and jumps by id; the cases pinned here are Gapless 0x4a015c, Gain 0x4a021c (nothing at all while the Line Out byte output_way is set), Digital Output
# 0x4a0418, Folder Album Cover 0x4a04a8 and Folder Skip 0x4a0504; the sub-pages' set functions are Memory Playback 0x49f608, ReplayGain 0x4a0f48, Digital Filter 0x49e95c, DSD Output Mode 0x4a61f8 and USB Audio
# Output 0x4af9a4 (Play Mode is pod_set_mode, tools/pod.py SHUFFLE_PINS). Each does its stores, saves and mcl calls in the order pinned here; the delay-slot stores (the byte of a switch, the word of Memory
# Playback and USB Audio Output) happen before the save's callee runs. The mcl getters and setters are pinned by their first words.
PLAYSET_PINS = (   # (address, stock word, what it proves)
    (0x49ffe8, 0x3c1c0056, 'playset click handler prologue (1/4)'),
    (0x49ffec, 0x279c3ee8, 'playset click handler prologue (2/4)'),
    (0x49fff0, 0x0399e021, 'playset click handler prologue (3/4)'),
    (0x49fff4, 0x27bdff90, 'playset click handler prologue (4/4)'),
    (0x4a0004, 0x00808025, 'playset click handler: move s0, a0 (the row item)'),
    (0x4a0014, 0x0320f809, 'playset click handler: jalr atoi (the item name is the row number)'),
    (0x4a0018, 0x8c840010, 'playset click handler: a0 = the name'),
    (0x4a0038, 0x1060000d, 'playset click handler: beqz (an id above 16 does nothing)'),
    (0x4a0164, 0x0320f809, 'Gapless click: jalr mclGetGaplessMode'),
    (0x4a0170, 0x38420001, 'Gapless click: new = state xor 1, as a byte (1/2)'),
    (0x4a0174, 0x305100ff, 'Gapless click: new = state xor 1, as a byte (2/2)'),
    (0x4a018c, 0x0320f809, 'Gapless click: jalr write_int_config(new, "PLAYSET", "GAPLESS")'),
    (0x4a019c, 0x0320f809, 'Gapless click: jalr mclSetGaplessMode(new) (1/2)'),
    (0x4a01a0, 0x02202025, 'Gapless click: jalr mclSetGaplessMode(new) (2/2)'),
    (0x4a0220, 0x90420000, 'Gain click: lbu output_way; bnez (Line Out: nothing) (1/2)'),
    (0x4a0224, 0x1440ff92, 'Gain click: lbu output_way; bnez (Line Out: nothing) (2/2)'),
    (0x4a0230, 0x0320f809, 'Gain click: jalr mclGetGainMode'),
    (0x4a023c, 0x2c440001, 'Gain click: new = (old == 0)'),
    (0x4a0258, 0x0320f809, 'Gain click: jalr write_int_config(new, "PLAYSET", "GAIN")'),
    (0x4a0260, 0x24050001, 'Gain click: a1 = 1 (store the word)'),
    (0x4a026c, 0x0320f809, 'Gain click: jalr mclSetGainMode(new, 1) (1/2)'),
    (0x4a0270, 0x8fa40058, 'Gain click: jalr mclSetGainMode(new, 1) (2/2)'),
    (0x4a043c, 0x38840001, 'Digital Output click: new = byte xor 1'),
    (0x4a0440, 0x0320f809, 'Digital Output click: jalr write_int_config(new, "PLAYSET", "DIGITALMODE"), the byte stored in its delay slot (1/2)'),
    (0x4a0444, 0xa2440000, 'Digital Output click: jalr write_int_config(new, "PLAYSET", "DIGITALMODE"), the byte stored in its delay slot (2/2)'),
    (0x4a0450, 0x0320f809, 'Digital Output click: jalr mclSetLineOut(the byte) (1/2)'),
    (0x4a0454, 0x92440000, 'Digital Output click: jalr mclSetLineOut(the byte) (2/2)'),
    (0x4a04cc, 0x38840001, 'Folder Album Cover click: new = byte xor 1'),
    (0x4a04d0, 0x0320f809, 'Folder Album Cover click: jalr write_int_config(new, "PLAYSET", "FOLDERCOVER"), the byte stored in its delay slot (1/2)'),
    (0x4a04d4, 0xa2440000, 'Folder Album Cover click: jalr write_int_config(new, "PLAYSET", "FOLDERCOVER"), the byte stored in its delay slot (2/2)'),
    (0x4a050c, 0x0320f809, 'Folder Skip click: jalr mclGetJumpFolder'),
    (0x4a0518, 0x38420001, 'Folder Skip click: new = state xor 1, as a byte (1/2)'),
    (0x4a051c, 0x305100ff, 'Folder Skip click: new = state xor 1, as a byte (2/2)'),
    (0x4a0534, 0x0320f809, 'Folder Skip click: jalr write_int_config(new, "PLAYSET", "JUMPFOLDER")'),
    (0x4a0544, 0x0320f809, 'Folder Skip click: jalr mclSetJumpFolder(new) (1/2)'),
    (0x4a0548, 0x02202025, 'Folder Skip click: jalr mclSetJumpFolder(new) (2/2)'),
    (0x49f73c, 0xae700000, 'Memory Playback set: the word stored in the delay slot of the save call'),
    (0x49f740, 0x0320f809, 'Memory Playback set: jalr write_int_config(i, "PLAYSET", "MEMORYPLAY")'),
    (0x4a106c, 0x0320f809, 'ReplayGain set: jalr mclSetReplayGain(i) (1/2)'),
    (0x4a1070, 0x02002025, 'ReplayGain set: jalr mclSetReplayGain(i) (2/2)'),
    (0x4a108c, 0x0320f809, 'ReplayGain set: jalr write_int_config(i, "PLAYSET", "REPLAYGAIN")'),
    (0x49ea80, 0x0320f809, 'Digital Filter set: jalr mclSetFilter(i) (1/2)'),
    (0x49ea84, 0x02002025, 'Digital Filter set: jalr mclSetFilter(i) (2/2)'),
    (0x49eaa0, 0x0320f809, 'Digital Filter set: jalr write_int_config(i, "PLAYSET", "FILTER")'),
    (0x4a632c, 0x0320f809, 'DSD set: jalr write_int_config(i, "SYSSET", "DSDMODE")'),
    (0x4a633c, 0x0320f809, 'DSD set: jalr mclGetOutputWay'),
    (0x4a6348, 0x14430005, 'DSD set: bne (only USB audio stops the player)'),
    (0x4a6354, 0x0320f809, 'DSD set: jalr save_stop_player'),
    (0x4a6364, 0x0320f809, 'DSD set: jalr mclSetDsdMode(i) (1/2)'),
    (0x4a6368, 0x02002025, 'DSD set: jalr mclSetDsdMode(i) (2/2)'),
    (0x4a6374, 0x0320f809, 'DSD set: jalr mclGetOutputWay again'),
    (0x4a6380, 0x14430004, 'DSD set: bne (only USB audio restarts the player)'),
    (0x4a638c, 0x0320f809, 'DSD set: jalr save_start_player(0) (1/2)'),
    (0x4a6390, 0x00002025, 'DSD set: jalr save_start_player(0) (2/2)'),
    (0x4afac8, 0xae330000, 'USB Audio Output set: the word stored'),
    (0x4afacc, 0x0320f809, 'USB Audio Output set: jalr set_devicevolume(volume) (1/2)'),
    (0x4afad0, 0x8c440000, 'USB Audio Output set: jalr set_devicevolume(volume) (2/2)'),
    (0x4afaec, 0x0320f809, 'USB Audio Output set: jalr write_int_config(the word, "SYSSET", "USBVOLMODE")'),
    (0x5d44b4, 0x3c1c0043, 'mclGetGaplessMode prologue'),
    (0x5d44b8, 0x279cfa1c, 'mclGetGaplessMode prologue'),
    (0x5d44bc, 0x0399e021, 'mclGetGaplessMode prologue'),
    (0x5d4450, 0x3c1c0043, 'mclGetJumpFolder prologue'),
    (0x5d4454, 0x279cfa80, 'mclGetJumpFolder prologue'),
    (0x5d4458, 0x0399e021, 'mclGetJumpFolder prologue'),
    (0x5d4468, 0x3c1c0043, 'mclSetJumpFolder prologue'),
    (0x5d446c, 0x279cfa68, 'mclSetJumpFolder prologue'),
    (0x5d4470, 0x0399e021, 'mclSetJumpFolder prologue'),
    (0x5d44cc, 0x3c1c0043, 'mclGetGainMode prologue'),
    (0x5d44d0, 0x279cfa04, 'mclGetGainMode prologue'),
    (0x5d44d4, 0x0399e021, 'mclGetGainMode prologue'),
    (0x5d5a4c, 0x3c1c0043, 'mclSetGainMode prologue'),
    (0x5d5a50, 0x279ce484, 'mclSetGainMode prologue'),
    (0x5d5a54, 0x0399e021, 'mclSetGainMode prologue'),
    (0x5d44e4, 0x3c1c0043, 'mclGetReplayGain prologue'),
    (0x5d44e8, 0x279cf9ec, 'mclGetReplayGain prologue'),
    (0x5d44ec, 0x0399e021, 'mclGetReplayGain prologue'),
    (0x5d292c, 0x3c1c0043, 'mclSetReplayGain prologue'),
    (0x5d2930, 0x279c15a4, 'mclSetReplayGain prologue'),
    (0x5d2934, 0x0399e021, 'mclSetReplayGain prologue'),
    (0x5d452c, 0x3c1c0043, 'mclGetfilter prologue'),
    (0x5d4530, 0x279cf9a4, 'mclGetfilter prologue'),
    (0x5d4534, 0x0399e021, 'mclGetfilter prologue'),
    (0x5d5b64, 0x3c1c0043, 'mclSetFilter prologue'),
    (0x5d5b68, 0x279ce36c, 'mclSetFilter prologue'),
    (0x5d5b6c, 0x0399e021, 'mclSetFilter prologue'),
    (0x5d44fc, 0x3c1c0043, 'mclGetDsdMode prologue'),
    (0x5d4500, 0x279cf9d4, 'mclGetDsdMode prologue'),
    (0x5d4504, 0x0399e021, 'mclGetDsdMode prologue'),
    (0x5d29d8, 0x3c1c0043, 'mclSetDsdMode prologue'),
    (0x5d29dc, 0x279c14f8, 'mclSetDsdMode prologue'),
    (0x5d29e0, 0x0399e021, 'mclSetDsdMode prologue'),
    (0x5d5e98, 0x3c1c0043, 'mclSetLineOut prologue'),
    (0x5d5e9c, 0x279ce038, 'mclSetLineOut prologue'),
    (0x5d5ea0, 0x0399e021, 'mclSetLineOut prologue'),
    # The three loudness pages (docs/modules/playset.md "Loudness pages"): stock's own refresh, click and value-changing handlers of maxvol_page, bootvol_page and balance_page, bound to our widgets by their names; each handler's reads,
    # stores, saves and calls in the order stock's code does them, the events and handlers stock's page init binds, and the Volume Memory click (ours repeats it).
    (0x49efec, 0x3c1c0056, 'Max Volume refresh 0x49efec: prologue'),
    (0x49f098, 0x24c6505c, 'refresh: a2 = "VOL: %d" (the label)'),
    (0x49f0b8, 0x0320f809, 'refresh: jalr slider_set_value (the slider at max_volume)'),
    (0x49f0cc, 0x0320f809, 'refresh: jalr widget_set_text_utf8 (label_vol)'),
    (0x49f0f4, 0x3c1c0056, 'Max Volume add 0x49f0f4: prologue'),
    (0x49f11c, 0x28440064, 'add: slti, max < 100'),
    (0x49f138, 0xac640000, 'add: sw max + 1 (delay slot of the save)'),
    (0x49f13c, 0x0320f809, 'add: jalr write_int_config(max, "PLAYSET", "MAXVOLUME")'),
    (0x49f16c, 0x3c1c0056, 'Max Volume dec 0x49f16c: prologue'),
    (0x49f19c, 0x18400023, 'dec: blez, max > 0'),
    (0x49f1ac, 0xae040000, 'dec: sw max - 1'),
    (0x49f1b4, 0x0082102a, 'dec: slt, max < volume'),
    (0x49f1c4, 0xae240000, 'dec: sw volume = max (delay slot of the output test)'),
    (0x49f1d0, 0x10620004, 'dec: beq headset_output == 2 skips the device call'),
    (0x49f1d8, 0x0320f809, 'dec: jalr set_devicevolume'),
    (0x49f1f4, 0x0320f809, 'dec: jalr write_int_config(volume, "PLAYSET", "VOLUME")'),
    (0x49f210, 0x0320f809, 'dec: jalr write_int_config(max, "PLAYSET", "MAXVOLUME")'),
    (0x49f24c, 0x3c1c0056, 'Max Volume slider 0x49f24c: prologue'),
    (0x49f28c, 0x0320f809, 'slider: jalr widget_get_prop_int(target, "value", 20)'),
    (0x49f298, 0x2c420065, 'slider: sltiu, value < 101'),
    (0x49f2bc, 0x10400011, 'slider: beqz, value < volume'),
    (0x49f2c0, 0xac640000, 'slider: sw max = value (delay slot)'),
    (0x49f2c8, 0xae040000, 'slider: sw volume = value'),
    (0x49f2d4, 0x10620004, 'slider: beq headset_output == 2'),
    (0x49f2dc, 0x0320f809, 'slider: jalr set_devicevolume'),
    (0x49f2f8, 0x0320f809, 'slider: jalr write_int_config(volume, "PLAYSET", "VOLUME")'),
    (0x49f314, 0x0320f809, 'slider: jalr write_int_config(max, "PLAYSET", "MAXVOLUME")'),
    (0x49f340, 0x0320f809, 'slider: jalr reset_poweroptions_timer(1, 1, 1)'),
    (0x49ee68, 0x2405010c, 'Max Volume page: click events 0x10c (shared by the buttons)'),
    (0x49ef68, 0x2405011d, 'page: widget_on(vol_slider, 0x11d, ..)'),
    (0x49ef6c, 0x24c6f24c, 'page: ... the slider handler 0x49f24c'),
    (0x49efb4, 0x24c6f16c, 'page: btn_dec -> 0x49f16c'),
    (0x49efe0, 0x24c6f0f4, 'page: btn_add -> 0x49f0f4'),
    (0x49d160, 0x3c1c0056, 'Default Volume refresh 0x49d160: prologue'),
    (0x49d194, 0x14a20037, 'refresh: bne mode != 1 (mode 1 writes the label and slider)'),
    (0x49d21c, 0x8f93ae04, 'refresh: lw boot_volume'),
    (0x49d250, 0x0320f809, 'refresh: jalr slider_set_value'),
    (0x49d264, 0x0320f809, 'refresh: jalr widget_set_text_utf8'),
    (0x49d39c, 0x3c1c0056, 'Default Volume dec 0x49d39c: prologue'),
    (0x49d3c0, 0x18400011, 'dec: blez, word > 0'),
    (0x49d3e0, 0xac640000, 'dec: sw word - 1 (delay slot of the save)'),
    (0x49d3e4, 0x0320f809, 'dec: jalr write_int_config(word, "PLAYSET", "BOOTVOLUME")'),
    (0x49d418, 0x3c1c0056, 'Default Volume slider 0x49d418: prologue'),
    (0x49d450, 0x8c440010, 'slider: widget_get_prop_int(target, "value", 20)'),
    (0x49d458, 0x2c420065, 'slider: sltiu, value < 101'),
    (0x49d478, 0xac440000, 'slider: sw word = value (delay slot of the save)'),
    (0x49d47c, 0x0320f809, 'slider: jalr write_int_config(word, "PLAYSET", "BOOTVOLUME")'),
    (0x49d4ac, 0x0320f809, 'slider: jalr reset_poweroptions_timer(1, 1, 1)'),
    (0x49d4c8, 0x3c1c0056, 'Default Volume add 0x49d4c8: prologue'),
    (0x49d4f0, 0x28440064, 'add: slti, word < 100'),
    (0x49d50c, 0xac640000, 'add: sw word + 1'),
    (0x49d510, 0x0320f809, 'add: jalr write_int_config(word, "PLAYSET", "BOOTVOLUME")'),
    (0x49cfd4, 0x2405010c, 'Default Volume page: click events 0x10c'),
    (0x49d0dc, 0x2405011d, 'page: widget_on(vol_slider, 0x11d, ..)'),
    (0x49d0e0, 0x24c6d418, 'page: ... the slider handler 0x49d418'),
    (0x49d0b0, 0x24c6d4c8, 'page: btn_add -> 0x49d4c8'),
    (0x49d128, 0x24c6d39c, 'page: btn_dec -> 0x49d39c'),
    (0x49d328, 0x3c1c0056, 'Volume Memory click 0x49d328: prologue'),
    (0x49d360, 0x90620000, 'Volume Memory: lbu boot_volflag'),
    (0x49d364, 0x38440001, 'Volume Memory: xori 1'),
    (0x49d368, 0x0320f809, 'Volume Memory: jalr write_int_config(byte, "PLAYSET", "BOOTVOLFLAG")'),
    (0x49d36c, 0xa0640000, 'Volume Memory: sb the byte (delay slot of the save)'),
    (0x49d34c, 0x24c670b0, 'Volume Memory: a2 = "BOOTVOLFLAG"'),
    (0x49cb8c, 0x3c1c0056, 'Channel Balance refresh 0x49cb8c: prologue'),
    (0x49cc2c, 0x1060001e, 'refresh: beqz, balance < 10'),
    (0x49cc3c, 0x24c67040, 'refresh: a2 = "L%d"'),
    (0x49ccac, 0x8f86a708, 'refresh: a2 = "R%d"'),
    (0x49ccc8, 0x0320f809, 'refresh: strcpy of the centre text'),
    (0x49cc6c, 0x0320f809, 'refresh: jalr slider_set_value'),
    (0x49cc80, 0x0320f809, 'refresh: jalr widget_set_text_utf8'),
    (0x49ccd8, 0x3c1c0056, 'Channel Balance add 0x49ccd8: prologue'),
    (0x49cd00, 0x28440014, 'add: slti, balance < 20'),
    (0x49cd1c, 0xac640000, 'add: sw balance + 1 (delay slot of the save)'),
    (0x49cd20, 0x0320f809, 'add: jalr write_int_config(balance, "PLAYSET", "BALANCE")'),
    (0x49cd4c, 0x10620006, 'add: beq headset_output == 2'),
    (0x49cd5c, 0x0320f809, 'add: jalr set_devicevolume(volume)'),
    (0x49ce4c, 0x3c1c0056, 'Channel Balance dec 0x49ce4c: prologue'),
    (0x49ce70, 0x1840001a, 'dec: blez, balance > 0'),
    (0x49ce90, 0xac640000, 'dec: sw balance - 1 (delay slot of the save)'),
    (0x49ce94, 0x0320f809, 'dec: jalr write_int_config(balance, "PLAYSET", "BALANCE")'),
    (0x49cec0, 0x10620006, 'dec: beq headset_output == 2'),
    (0x49ced0, 0x0320f809, 'dec: jalr set_devicevolume(volume)'),
    (0x49cd78, 0x3c1c0056, 'Channel Balance slider 0x49cd78: prologue'),
    (0x49cdac, 0x0320f809, 'slider: jalr widget_get_prop_int(target, "value", 20)'),
    (0x49cdb8, 0x2c420015, 'slider: sltiu, value < 21'),
    (0x49cdd8, 0xac440000, 'slider: sw balance = value (delay slot of the save)'),
    (0x49cddc, 0x0320f809, 'slider: jalr write_int_config(balance, "PLAYSET", "BALANCE")'),
    (0x49ce08, 0x10620007, 'slider: beq headset_output == 2'),
    (0x49ce18, 0x0320f809, 'slider: jalr set_devicevolume(volume)'),
    (0x49ce30, 0x0320f809, 'slider: jalr reset_poweroptions_timer(1, 1, 1)'),
    (0x49ca08, 0x2405010c, 'Channel Balance page: click events 0x10c'),
    (0x49cb08, 0x2405011d, 'page: widget_on(slider_balance, 0x11d, ..)'),
    (0x49cb0c, 0x24c6cd78, 'page: ... the slider handler 0x49cd78'),
    (0x49cb54, 0x24c6ce4c, 'page: btn_dec -> 0x49ce4c'),
    (0x49cb80, 0x24c6ccd8, 'page: btn_add -> 0x49ccd8'),
)

LIGHT_PINS = (   # (address, stock word, what it proves)
    (0x659fd8, 0x27bdff80, 'style_get_color: addiu sp, sp, -0x80 (the trampoline resumes here)'),
    (0x65a048, 0x0411ffd4, 'style_get_color: bal style_get_gradient (0x659f9c), returning to STYLE_COLOR_GRADIENT_RET: unmapped there'),
    (0x65a050, 0x8fbc0010, 'style_get_color: lw gp, 0x10(sp) at the gradient call\'s return address'),
    (0x65a080, 0x8c590014, 'style_get_color: lw t9, 0x14(v0): the style\'s get_color slot, called when the style has no gradient'),
    (0x659fb0, 0x8c590018, 'style_get_gradient: lw t9, 0x18(v0): the get_gradient slot (the leaf the hook reimplements)'),
    (0x659fb4, 0x13200003, 'style_get_gradient: beqz t9, return 0'),
    (0x655644, 0x10800075, 'image_manager_add: beqz a0 (the trampoline resumes here)'),
    (0x655adc, 0x0411fed6, 'image_manager_lookup: bal image_manager_add (the first of the only two callers: a decoded image is added once, before it is cached)'),
    (0x655b50, 0x0411feb9, 'image_manager_lookup: bal image_manager_add (the second)'),
    (0x655694, 0x0320f809, 'image_manager_add: jalr tk_calloc: the manager copies the bitmap_t it is given (memcpy 0x48 at 0x6556b4), sharing its pixel buffer'),
    (0x6556b4, 0x0320f809, 'image_manager_add: jalr memcpy(copy, bitmap_t, 0x48)'),
    (0x655ff4, 0x03200008, 'image_manager_unload_all: jr darray_clear (times are not looked at)'),
)
SONGS_PINS = (   # (address, stock word, what it proves): prologues are `lui $gp, hi; addiu $gp, $gp, lo; addu $gp, $gp, $t9`
    (0x4da3b0, 0x3c1c0053, 'select_recordinit prologue'), (0x4da3b4, 0x279c9b20, 'select_recordinit prologue'), (0x4da3b8, 0x0399e021, 'select_recordinit prologue'),
    (0x4da3bc, 0x0480001b, 'select_recordinit: bltz a0 (a negative count does nothing)'),
    (0x4da3a0, 0x8f82ac50, 'clear_selectrecord: lw v0, GOT 0xa045e0 (SEL_VEC: the selection vector\'s pointer)'), (0x4da3ac, 0x8c440000, 'clear_selectrecord: a0 = *SEL_VEC, vector_clear(a0)'),
    (0x4da434, 0x3c1c0053, 'set_selectindex prologue'), (0x4da438, 0x279c9a9c, 'set_selectindex prologue'), (0x4da43c, 0x0399e021, 'set_selectindex prologue'),
    (0x4e1408, 0x3c1c0052, 'batch_delete_file prologue'), (0x4e140c, 0x279c2ac8, 'batch_delete_file prologue'), (0x4e1410, 0x0399e021, 'batch_delete_file prologue'),
    (0x4e1418, 0x3402f00c, 'batch_delete_file: class < 0xf00c (the jump tables\' range)'),
    (0x4d1d80, 0x3c1c0053, 'navigator_to prologue'), (0x4d1d90, 0x1000ffed, 'navigator_to: b navigator_to_with_context (0x4d1d48)'), (0x4d1d94, 0x00002825, 'navigator_to: with a1 = 0 (the delay slot)'),
    (0x52704c, 0x3c1c004e, 'the Songs page\'s search click handler prologue'), (0x52705c, 0x8f848020, 'search handler: lw a0, GOT page'),
    (0x527070, 0x24849e00, 'search handler: a0 = "search_page" (navigator_to("search_page"), no context, nothing set first)'),
    (0x527014, 0x3c1c004e, 'the Songs page\'s sort click handler prologue'), (0x527038, 0x24849db0, 'sort handler: a0 = "dialog/sortselect_dialog" (navigator_to, no context)'),
    (0x47d1a8, 0x24c64f90, 'sortselect row handler 0x47d114: a2 = "SORTSELECT"'), (0x47d1ac, 0x24a54540, 'sortselect row handler: a1 = "SYSSET"'),
    (0x47d1b0, 0x8c640000, 'sortselect row handler: a0 = sortMenu[i] (0x97c770: 0 1 2 3 4)'), (0x47d1b4, 0x0320f809, 'sortselect row handler: jalr write_int_config'),
    (0x47d1b8, 0xae640000, 'sortselect row handler: sw a0, (s3) in the delay slot: sort_flag (0xa059d4) = the choice'),
    (0x4d9d64, 0x3c1c0053, 'is_playing prologue'), (0x4d9d68, 0x279ca16c, 'is_playing prologue'), (0x4d9d6c, 0x0399e021, 'is_playing prologue'),
    (0x524c40, 0x8c460008, 'album row builder 0x524b50: a2 = record + 8 (the file name), the 3rd argument of is_playing'), (0x524c44, 0x8c47000c, 'album row builder: a3 = record + 0xc (the url)'),
    (0x524c48, 0x8c450048, 'album row builder: a1 = record + 0x48 (the CUE start)'), (0x524c4c, 0x8f82ac00, 'album row builder: v0 = &g_class_type (GOT 0x97cad4)'),
    (0x524c54, 0x0320f809, 'album row builder: jalr is_playing'), (0x524c58, 0x8c440000, 'album row builder: a0 = g_class_type (the delay slot)'),
    # The Queue page (patch/queuepage.c): the queue drawer the Now Playing queue button opens (handler 0x53b14c: navigator_to("dialog/playqueue_dialog")), its row marker and its row handler
    (0x53b178, 0x0320f809, 'queue button handler 0x53b14c: jalr navigator_to'), (0x53b17c, 0x24849f90, 'queue button handler: a0 = "dialog/playqueue_dialog" (the delay slot)'),
    (0x47a014, 0x2602fffe, 'row handler 0x479f60: a stream while offline: the play type s0 - 2 < 2 ...'), (0x47a018, 0x2c420002, '... (types 2, 3)'),
    (0x47a020, 0x2602ff10, '... or s0 - 0xf0 < 2'), (0x47a024, 0x2c420002, '... (types 0xf0, 0xf1: the message, no play)'),
    (0x47a0c4, 0x8f99aa9c, 'row handler: t9 = start_playqueue'), (0x47a0c8, 0x0320f809, 'row handler: jalr start_playqueue'), (0x47a0cc, 0x02402025, 'row handler: a0 = the row (move a0, s2)'),
    (0x539888, 0x3c1c004d, 'Now Playing mode button picture prologue'), (0x53988c, 0x279ca648, 'mode button picture prologue'), (0x539890, 0x0399e021, 'mode button picture prologue'),
    (0x5398a8, 0x24a51cc8, 'mode button picture: a1 = "btn_playmode"'), (0x5398cc, 0x0320f809, 'mode button picture: jalr mclGetPlayMode'),
    (0x53b67c, 0x0411f882, 'mode button click handler 0x53b5fc: bal 0x539888 (after mclSetPlayMode and write_int_config)'), (0x53b680, 0x02202025, 'mode button click handler: a0 = the handler\'s own a0 (move a0, s1)'),
    (0x4e47d0, 0x3c1c0052, 'start_playqueue prologue'), (0x4e47d4, 0x279cf700, 'start_playqueue prologue'), (0x4e47d8, 0x0399e021, 'start_playqueue prologue'),
    (0x5d3658, 0x3c1c0043, 'mclGetPlayType prologue'), (0x5d365c, 0x279c0878, 'mclGetPlayType prologue'), (0x5d3660, 0x0399e021, 'mclGetPlayType prologue'),
    (0x5d4290, 0x3c1c0043, 'mclGetPlayPos prologue'), (0x5d4294, 0x279cfc40, 'mclGetPlayPos prologue'), (0x5d4298, 0x0399e021, 'mclGetPlayPos prologue'),
    (0x524c94, 0x8e220048, 'album row builder: a track whose CUE start (+0x48) ...'), (0x524c98, 0x1c400004, '... is > 0 shows its file name (bgtz)'),
    (0x524ca0, 0x8e22004c, 'album row builder: or whose CUE end (+0x4c)'), (0x524ca4, 0x1840001f, '... is > 0 (blez to the title path 0x524d24: record + 0x10, else the file name)'),
)
IPOD_PINS = (   # (address, stock word, what it proves)
    (0x4cccb0, 0x3c1c0053, 'prev_quick_click prologue'), (0x4cccb4, 0x279c7220, 'prev_quick_click prologue'), (0x4cccb8, 0x0399e021, 'prev_quick_click prologue'),
    (0x4cccdc, 0x8c850008, 'prev_quick_click: lw a1, 8(a0): the event time (as next_quick_click @0x4ccf2c)'),
    (0x4cccf8, 0x284203e8, 'prev_quick_click: slti v0, v0, 1000: the 1 s guard'),
    (0x4eea98, 0x3c1c0051, 'loadAlbumdetailList prologue'), (0x4eea9c, 0x279c5438, 'loadAlbumdetailList prologue'), (0x4eeaa0, 0x0399e021, 'loadAlbumdetailList prologue'),
    (0x4eeaa8, 0x3402f003, 'loadAlbumdetailList: class 0xf003 (the Albums list)'), (0x4eeab8, 0x00a08825, 'loadAlbumdetailList: s1 = a1 (or s1, a1, zero), the album record'),
    (0x4eeacc, 0x8e220000, 'loadAlbumdetailList: lw v0, (s1): the record id'),
    (0x663840, 0x3c1c003a, 'timer_modify prologue'), (0x663844, 0x279c0690, 'timer_modify prologue'), (0x663848, 0x0399e021, 'timer_modify prologue'),
    (0x66389c, 0xae110040, 'timer_modify: sw s1, 0x40(s0): the timer\'s duration'),
)
WIFIHUB_SITE = 0x4b1460   # the Wi-Fi row of the All System Settings hub: its jalr navigator_to("systemset/wifi_page") becomes jal wifi_hub_open (patch/wifipage.c, docs/modules/payload.md hook 21)
# The stock Tidal > Search page's T9 (patch/tidalkb.c, docs/modules/tidalkb.md, payload hook 27): the bind callback 0x4c1f3c of tidal_tidal_serach_page_init calls edit_set_focus(search_edit, 1) at 0x4c2088
# (lw t9 GOT @0x4c2080, a1 = 1 @0x4c2084, delay slot move a0, s0 @0x4c208c); that jalr becomes jal tidal_kb_focus. Stock's search routine 0x4c4740 (called by the IM action handler 0x4c4990 with the window's widget) is
# called by the payload with the edit. Stock facts the design stands on are pinned too: widget_dispatch running the emitter unless on_event answers RET_STOP (a view has no on_event), the list_item's click, and the history row click writing the keyword into search_edit.
TIDALKB_SITE = 0x4c2088
TIDALKB_PINS = (   # (address, stock word, what it proves)
    (0x4c1f3c, 0x3c1c0054, 'Tidal search bind callback prologue'), (0x4c1f40, 0x279c1f94, 'Tidal search bind callback prologue'), (0x4c1f44, 0x0399e021, 'Tidal search bind callback prologue'),
    (0x4c1f7c, 0x00a08025, 'bind callback: move s0, a1 (the widget)'), (0x4c2070, 0x24a56ad0, 'bind callback: a1 = "search_edit" (strcmp)'), (0x4c2078, 0x14400051, 'bind callback: bnez v0 (not search_edit: next widget)'),
    (0x4c2080, 0x8f99a8a8, 'bind callback: lw t9, GOT edit_set_focus'), (0x4c2084, 0x24050001, 'bind callback: a1 = 1'), (TIDALKB_SITE, 0x0320f809, 'bind callback: jalr edit_set_focus'),
    (0x4c208c, 0x02002025, 'its delay slot: move a0, s0 (the edit)'), (0x4c2090, 0x2405013c, 'bind callback: a1 = 0x13c (IM action) for the widget_on that follows'), (0x4c20ac, 0x24c64990, 'bind callback: a2 = 0x4c4990 (the action handler)'),
    (0x4c4740, 0x3c1c0054, 'Tidal search routine prologue'), (0x4c4744, 0x279cf790, 'Tidal search routine prologue'), (0x4c4748, 0x0399e021, 'Tidal search routine prologue'),
    (0x4c4a00, 0x0411ff4f, 'action handler 0x4c4990: bal 0x4c4740(window widget, event)'), (0x4c4a04, 0x02202025, 'its delay slot: move a0, s1 (the page, not the event)'),
    (0x62a1dc, 0x3c1c003e, 'edit_set_focus prologue'), (0x62a1e0, 0x279c9cf4, 'edit_set_focus prologue'), (0x62a1e4, 0x0399e021, 'edit_set_focus prologue'),
    # re-search: the tab buttons reset a result struct before 0x4c2380 (tab word 0xa04158, limit 0x32 at +4, deque_clear of *(+0xc), offset 0 at +8, scroll 0xa04150 = 0); 0x4c2380 picks the struct by the tab
    # (0 tracks 0xa10264 / thread 0x51f164, 1 artists 0xa10254 / 0x52061c, 2 albums 0xa10244 / 0x51f338, the offset passed as the thread argument); the parse pushes onto *(tracks + 0xc); the timer restores 0xa04150
    (0x4c2888, 0xac404158, 'btn_track 0x4c2854: tab = 0'), (0x4c2898, 0x8f82b118, 'btn_track: GOT tracks struct 0xa10264'), (0x4c289c, 0x24030032, 'btn_track: limit 0x32'),
    (0x4c28a4, 0x8c44000c, 'btn_track: a0 = *(tracks + 0xc)'), (0x4c28a8, 0xac430004, 'btn_track: limit at +4'), (0x4c28ac, 0x0320f809, 'btn_track: jalr deque_clear'), (0x4c28b0, 0xac400008, 'btn_track: offset 0 at +8'),
    (0x4c28c8, 0x0411fead, 'btn_track: bal 0x4c2380'), (0x4c28cc, 0xac404150, 'btn_track: scroll offset 0xa04150 = 0 (delay slot)'),
    (0x4c2774, 0x8f82b110, 'btn_album 0x4c272c: GOT albums struct 0xa10244'), (0x4c2778, 0x24030032, 'btn_album: limit 0x32'), (0x4c2784, 0xac430004, 'btn_album: limit at +4'),
    (0x4c2788, 0x0320f809, 'btn_album: jalr deque_clear'), (0x4c278c, 0xac400008, 'btn_album: offset 0'), (0x4c27a4, 0x0411fef6, 'btn_album: bal 0x4c2380'), (0x4c27a8, 0xac404150, 'btn_album: scroll 0'),
    (0x4c2808, 0x8f82b120, 'btn_artist 0x4c27c0: GOT artists struct 0xa10254'), (0x4c2818, 0xac430004, 'btn_artist: limit at +4'), (0x4c281c, 0x0320f809, 'btn_artist: jalr deque_clear'),
    (0x4c2820, 0xac400008, 'btn_artist: offset 0'), (0x4c2838, 0x0411fed1, 'btn_artist: bal 0x4c2380'), (0x4c283c, 0xac404150, 'btn_artist: scroll 0'),
    (0x4c2434, 0x8c424158, 'search 0x4c2380: lw tab 0xa04158'), (0x4c2438, 0x14400015, 'search: tab != 0 -> other tabs'), (0x4c2440, 0x8f82b118, 'search: tab 0 = tracks struct 0xa10264'),
    (0x4c2444, 0x8f86b11c, 'search: tab 0 thread 0x51f164'), (0x4c2448, 0x8c470008, 'search: thread argument = the struct offset (+8)'),
    (0x4c2498, 0x8f82b120, 'search: tab 1 = artists struct 0xa10254'), (0x4c249c, 0x8f86b124, 'search: tab 1 thread 0x52061c'), (0x4c24b0, 0x8f82b110, 'search: tab 2 = albums struct 0xa10244'), (0x4c24b4, 0x8f86b114, 'search: tab 2 thread 0x51f338'),
    (0x5200e4, 0x8f82b118, 'parseTidalSearchTracksJson: GOT tracks struct'), (0x5200f0, 0x0320f809, 'parse: jalr _deque_push_back'), (0x5200f4, 0x8c44000c, 'parse: a0 = *(tracks + 0xc) (delay slot)'),
    (0x4c3c38, 0x8c424158, 'result timer 0x4c3bb4: lw tab'), (0x4c3c70, 0x8c664150, 'result timer: scroll_view_set_offset with 0xa04150 (delay slot lw a2)'),
    # the tap: the field is the bar's child and a view has no on_event (vtable slot 0x94 is NULL: widget_dispatch goes on to the emitter), so the touch reaches the list_item holding the bar, which sends
    # EVT_CLICK (list_item_on_event 0x60bb80, pointer up case: no drag and pressed -> event_init 0x10c, widget_dispatch on itself); widget_on_pointer_down 0x67126c runs the parent's widget_dispatch after the child
    # unless the child answered RET_STOP
    (0x60bd58, 0x9222007c, 'list_item pointer up: lbu v0, 0x7c(s1): the dragged flag'), (0x60bd68, 0x1040001a, 'list_item pointer up: beqz pressed (0x7d): no click'),
    (0x60bd8c, 0x2405010c, 'list_item pointer up: event_init type 0x10c (EVT_CLICK)'), (0x60bdcc, 0x0320f809, 'list_item pointer up: widget_dispatch of the click on the list_item itself'),
    (0x67133c, 0x1051003b, 'widget_on_pointer_down: a child answering RET_STOP skips the parent'), (0x67134c, 0x0411eede, 'widget_on_pointer_down: bal widget_dispatch (the parent, after its children)'),
    (0x67199c, 0x14530014, 'widget_on_pointer_up: a child answering RET_STOP skips the parent'), (0x6719fc, 0x0411f209, 'widget_on_pointer_up: bal 0x66e224 (widget_dispatch, then the vtable pointer-up slot; the parent, after its children)'),
    (0x674824, 0x8c90004c, 'widget_find_target_default: lw s0, 0x4c(a0): a grabbed child is the target'),
    (0x66cf2c, 0x8c590094, 'widget_dispatch: lw t9, 0x94(v0): the vtable on_event'), (0x66cf30, 0x1320001e, 'widget_dispatch: no on_event (a view) -> straight to the emitter'),
    (0x4c2254, 0x3c1c0054, 'Tidal search page state routine (win, 1): hides the history, shows the results, writes the keyword into search_edit'), (0x4c2edc, 0x0411fcdd, 'history row click: bal 0x4c2254 after copying the row into the keyword buffer'),
    # the navbar's Search button: the page init creates it (button_create(navbar, x 0x111, y 0, w 0x2f, h 0x32), the last child of the navbar when the widget_foreach that runs the hook starts) and binds EVT_CLICK 0x10c -> 0x4c4740 with the
    # window as context; the emitter runs the newest handler first and RET_STOP ends the dispatch (payload tk_on_search_btn)
    (0x4c4a74, 0x8f99ab64, 'page init: lw t9, GOT button_create'), (0x4c4a78, 0x24020032, 'page init: button h = 0x32 (stack arg)'), (0x4c4a7c, 0x2407002f, 'page init: button w = 0x2f'), (0x4c4a80, 0x00003025, 'page init: button y = 0'),
    (0x4c4a88, 0x0320f809, 'page init: jalr button_create'), (0x4c4a8c, 0x24050111, 'page init: button x = 0x111 (delay slot)'), (0x4c4aac, 0x2405010c, 'page init: widget_on(button, EVT_CLICK 0x10c, ...)'),
    (0x4c4ab4, 0x02003825, 'page init: a3 = the window (the context)'), (0x4c4ac4, 0x0320f809, 'page init: jalr widget_on'), (0x4c4ac8, 0x24c64740, 'page init: a2 = 0x4c4740 (the stock search; delay slot)'),
    (0x4c4bc8, 0x0320f809, 'page init: jalr widget_foreach (the hook runs inside; nothing is added to the navbar between the button and here)'),
    (0x6f450c, 0x2402000b, 'emitter_dispatch: RET_STOP (11) ends the dispatch'),
    (0x6f466c, 0xac430020, 'emitter_on_with_tag: new->next = emitter->items'), (0x6f4670, 0xae020000, 'emitter_on_with_tag: emitter->items = new (a handler goes to the head: the newest runs first)'),
    (0x66cf38, 0x0320f809, 'widget_dispatch: jalr the vtable on_event'), (0x66cf48, 0x2402000b, 'widget_dispatch: v0 = 0xb (RET_STOP)'), (0x66cf4c, 0x1202000d, 'widget_dispatch: on_event == RET_STOP skips the emitter'),
)
SETTINGS_PINS = (   # (address, stock word, what it proves)
    # the stock pages: each is a plain navigator_to of the name (the string load is the word before the call's delay slot or the shared call), nothing else set first
    # the Wi-Fi hub row's thunk @0x4b1440 (payload hook 21): its jalr navigator_to @0x4b1460 becomes jal wifi_hub_open; the thunk's prologue, GOT loads, delay slot and return value are stock's
    (0x4b1440, 0x3c1c0055, 'the Wi-Fi hub row thunk prologue'), (0x4b1444, 0x279c2a90, 'the Wi-Fi hub row thunk prologue'), (0x4b1448, 0x0399e021, 'the Wi-Fi hub row thunk prologue'),
    (0x4b1450, 0x8f848020, 'the Wi-Fi hub row: lw a0, GOT page 0x750000'), (0x4b1454, 0x8f99a704, 'the Wi-Fi hub row: lw t9, GOT navigator_to'),
    (WIFIHUB_SITE, 0x0320f809, 'the Wi-Fi hub row (0x4b1440): jalr navigator_to'), (0x4b1464, 0x24848f1c, 'its delay slot: a0 = "systemset/wifi_page"'), (0x4b1468, 0x00001025, 'the Wi-Fi hub row: move v0, zero (the result is not used)'),
    (0x4b1428, 0x0320f809, 'the Bluetooth hub row (0x4b1410): jalr navigator_to'), (0x4b142c, 0x24848f00, 'its delay slot: a0 = "systemset/bluetooth_page"'),
    (0x4ad830, 0x0320f809, 'the Settings rows\' shared call: jalr navigator_to'), (0x4ada74, 0x24848ab4, 'Settings row 3: a0 = "systemset/display_page" (our Display page takes its place)'),
    (0x4ada38, 0x24848a68, 'Settings row 1: a0 = "systemset/fwupdate_page"'),
    # About: the stock page's values (the widget walk's callback inside what the symbol table calls on_sn_qrcode_onclick, @0x4a1240..0x4a170c; the init 0x4a170c-): the model and firmware version literals, the card
    # numbers (access /tmp/mmc_add, then getDiskMemoryInfo("/mnt/mmc", &cap 0xa03e74, &rem 0xa03e70)), the serial number and the Wi-Fi MAC strings, the IP address
    (0x4a145c, 0x24427718, 'about row 0: v0 = "Shanling M1 Plus" (the model literal)'), (0x4a14cc, 0x2442773c, 'about row 1: v0 = "V2.1" (the firmware version literal)'),
    (0x747718, 0x6e616853, 'the model literal reads "Shan.." (Shanling M1 Plus)'), (0x74773c, 0x312e3256, 'the version literal reads "V2.1"'),
    (0x4a1514, 0xc4403e74, 'about row 2: lwc1 f0, 0x3e74(v0): the card capacity'), (0x4a1634, 0xc4403e70, 'about row 4: lwc1 f0, 0x3e70(v0): the card free space'),
    (0x4a1754, 0x248477a4, 'about init: a0 = "/tmp/mmc_add" (access: the card is in)'), (0x4a177c, 0x24844bd0, 'about init: a0 = "/mnt/mmc" (getDiskMemoryInfo)'),
    (0x4a1778, 0x0320f809, 'about init: jalr getDiskMemoryInfo'), (0x4a1774, 0x26253e74, 'about init: a1 = &capacity (s1 + 0x3e74)'), (0x4a176c, 0x26463e70, 'about init: a2 = &free space (s2 + 0x3e70)'),
    (0x4a16dc, 0x0320f809, 'about row 6: jalr networkGetConnectStatus'), (0x4a16f4, 0x0320f809, 'about row 6: jalr networkGetIPAddr(0, buf), only while it says connected'),
    # EQ: the on/off byte and the preset's name (the toggle handler 0x49d750 and the name lookup)
    (0x49d774, 0x24c670d8, 'eq switch: a2 = "EQFLAG"'), (0x49d77c, 0x24a54264, 'eq switch: a1 = "PLAYSET"'), (0x49d788, 0x90620000, 'eq switch: lbu v0, (v1): equalizer_flag'),
    (0x49d78c, 0x38440001, 'eq switch: xori a0, v0, 1: the flag flipped, saved by write_int_config, stored back'),
    (0x49daec, 0x3c1c0056, 'get_equalizer_preset_name prologue'), (0x49daf0, 0x279c63e4, 'get_equalizer_preset_name prologue'), (0x49daf4, 0x0399e021, 'get_equalizer_preset_name prologue'),
    (0x49daf8, 0x2c83000c, 'get_equalizer_preset_name: sltiu v1, a0, 12: a preset 0..11, else it returns 0'),
)
FONT_PINS = (   # (address, stock word, what it proves): the stb font layout patch/offsets.inc FONT_* names
    (0x67ef14, 0x240500d4, 'font_stb_create_ex: tk_calloc(1, 0xd4): the font object'),
    (0x67ef48, 0xafc20020, 'font_stb_create_ex: sw match (0x67d2d4) @+0x20'), (0x67ef60, 0xafc20024, 'font_stb_create_ex: sw get_glyph (0x680228) @+0x24'),
    (0x67f030, 0xafd7003c, 'font_stb_create_ex: sw s7 @+0x3c: stbtt_fontinfo data'), (0x67f038, 0xafd60040, 'font_stb_create_ex: sw s6 @+0x40: fontstart'),
    (0x67f74c, 0x02a21021, 'stbtt_InitFont: addu v0, s5, v0: cmap + the record\'s subtable offset'),
    (0x67f758, 0xafc20064, 'stbtt_InitFont: sw v0 @+0x64: index_map (the last record of platform 0 or 3/1, 3/10 wins)'),
    (0x67c3c0, 0x8c870004, 'stbtt_FindGlyphIndex: lw a3, 4(a0): data, read on every lookup'),
    (0x67c3c4, 0x8c88002c, 'stbtt_FindGlyphIndex: lw t0, 0x2c(a0): index_map (fontinfo +0x2c = font +0x64), read on every lookup'),
    (0x680300, 0x02c02025, 'font_stb_get_glyph: move a0, s6: the fontinfo it looks glyphs up in'),
    (0x658970, 0x26120003, 'locale_info_reload: addiu s2, s0, 3: the language at +3'), (0x658978, 0xafb00010, 'locale_info_reload: the country at +0, the second %s'),
    (0x658a7c, 0x24050122, 'locale_info_change: EVT_LOCALE_CHANGED 0x122'), (0x658bc8, 0x24050122, 'locale_info_on: emitter_on with 0x122'),
    (0x66d4bc, 0x2405014a, 'widget_set_theme: EVT_THEME_CHANGED 0x14a, dispatched on the window manager after font_manager_unload_all'),
    (0x74a988, 0x61666564, 'the stock font name "default" (main: system_info_set_default_font)'), (0x74a98c, 0x00746c75, '"default" (cont.)'),
)
GLYPH_CACHE_LOOKUP = 0x6a4204   # static in demo (no .dynsym entry, so not in FUNCTIONS): called by font_stb_get_glyph before it rasterizes
TEXTGAMMA_PINS = (   # (address, stock word, what it proves): the glyph path patch/textgamma.c wraps (docs/modules/fonts.md "Coverage gamma")
    (GLYPH_CACHE_LOOKUP, 0x3c1c0036, 'glyph_cache_lookup: lui gp, 0x36 (its first word; 0 on a hit)'),
    (0x6a4214, 0x1080000e, 'glyph_cache_lookup: beqz a0 (the cache)'),
    (0x6a4224, 0x8c670000, 'glyph_cache_lookup: lw a3, 0(v1): the cache\'s entry count, first word of the scan'),
    (0x6a41e8, 0xae12000c, 'glyph_cache_add: sw s2, 0xc(s0): the entry keeps the glyph\'s character (a miss is cached here)'),
    (0x6802d8, 0x264200b4, 'font_stb_get_glyph: addiu v0, s2, 0xb4: the glyph cache at font +0xb4 (FONT_CACHE)'),
    (0x680458, 0x924200d0, 'font_stb_get_glyph: lbu v0, 0xd0(s2): the mono flag at font +0xd0 (FONT_MONO)'),
    (0x6803cc, 0xa200000a, 'font_stb_get_glyph: sb zero, 0xa(s0): the glyph format 0 = 8-bit alpha (GLYPH_FORMAT)'),
    (0x68040c, 0xa2030004, 'font_stb_get_glyph: sb v1, 4(s0): the glyph w (GLYPH_W), from 0x8c(sp)'),
    (0x680424, 0xa2030006, 'font_stb_get_glyph: sb v1, 6(s0): the glyph h (GLYPH_H), from 0x90(sp)'),
    (0x680864, 0x70432002, 'font_stb_get_glyph: mul a0, v0, v1: the bitmap is w * h bytes, stride w (tk_alloc at 0x680868)'),
    (0x6805e0, 0x10400253, 'font_stb_get_glyph: beqz v0 after glyph_cache_add: 0 is success; the out copy keeps the bitmap pointer (GLYPH_DATA)'),
)
ID3_SITE = 0x4dff4c   # get_id3info's jalr strcpy of the parsed path, replaced by jal pc_id3_path (docs/modules/podcasts.md "Tags"); q2-pod's ID3_PATH is the same site in its demo
PODCAST_PINS = (   # (address, stock word, what it proves)
    (0x4e0544, 0x3c1c0052, 'seek_time prologue'), (0x4e0548, 0x279c398c, 'seek_time prologue'), (0x4e054c, 0x0399e021, 'seek_time prologue'),
    (0x4e0560, 0x00808025, 'seek_time: move s0, a0: the target in seconds'),
    (0x4e05f0, 0x8c440048, 'seek_time: lw a0, 0x48(v0): the playing record\'s CUE start'),
    (0x4e05fc, 0x02048021, 'seek_time: addu s0, s0, a0 (delay slot): target + CUE start'),
    (0x4e0608, 0x0320f809, 'seek_time: jalr mclSetSeek'),
    (0x5d281c, 0x3c1c0043, 'mclSetPlaySpeed prologue'), (0x5d2820, 0x279c16b4, 'mclSetPlaySpeed prologue'), (0x5d2824, 0x0399e021, 'mclSetPlaySpeed prologue'),
    (0x4dfd58, 0x3c1c0052, 'get_id3info prologue'), (0x4dfd5c, 0x279c4178, 'get_id3info prologue'), (0x4dfd60, 0x0399e021, 'get_id3info prologue'),
    (0x4dfff8, 0x26250404, 'get_id3info: addiu a1, s1, 0x404: toolsGetMusicInfo(0, id3 + 0x404, path) fills album / artist / title from the tags'),
    (0x4e0000, 0x0320f809, 'get_id3info: jalr toolsGetMusicInfo'),
    (0x4dff40, 0x8f99f324, 'get_id3info: lw t9, GOT strcpy (the call site the tag hook replaces)'), (0x4dff44, 0x8f84aa64, 'get_id3info: lw a0, GOT playsong_id3info'),
    (0x4dff48, 0xae220400, 'get_id3info: sw v0, 0x400(s1): the CUE start into the struct'), (ID3_SITE, 0x0320f809, 'get_id3info: jalr strcpy(info, path): every fresh parse passes it, after toolsGetMusicInfo and the fallbacks of the fields'),
    (0x4dff50, 0x8e05000c, 'get_id3info: lw a1, 0xc(s0) (delay slot): the record\'s path; s0 = the record, s1 = the struct'), (0x4dff58, 0x8f99f524, 'get_id3info: lw t9, GOT memset: song_name / song_artist are built after the site'),
    (0x4dff74, 0x82220684, 'get_id3info: lb v0, 0x684(s1): an empty title takes the file name'), (0x4dffac, 0x82220504, 'get_id3info: lb v0, 0x504(s1): an empty artist takes "Unknown"'),
    (0x5d2830, 0x00803025, 'mclSetPlaySpeed: move a2, a0: the mode is the %d of "{mcl-playspeed\\%d}"'),
    # reset_poweroptions_timer(a0, a1, a2) 0x4d7874 (Podcast downloads keep the device awake with (1, 1, 0)): a0 -> setstandby_time (standby), a1 -> setsavepower_time (auto power-off), a2 -> setlight_time (the screen's light)
    (0x4d7874, 0x3c1c0053, 'reset_poweroptions_timer prologue'), (0x4d7878, 0x279cc65c, 'reset_poweroptions_timer prologue'), (0x4d787c, 0x0399e021, 'reset_poweroptions_timer prologue'),
    (0x4d788c, 0x00c08025, 'reset_poweroptions_timer: move s0, a2 (the screen argument)'), (0x4d7894, 0x00a08825, 'reset_poweroptions_timer: move s1, a1 (the auto power-off argument)'),
    (0x4d7898, 0x10800008, 'reset_poweroptions_timer: beqz a0: the standby countdown is set again only for a non-zero first argument'),
    (0x4d78a8, 0x0411ffe0, 'reset_poweroptions_timer: bal setstandby_time 0x4d782c'),
    (0x4d78bc, 0x12200007, 'reset_poweroptions_timer: beqz s1: auto power-off only for a non-zero second argument'),
    (0x4d78c8, 0x0411ffdc, 'reset_poweroptions_timer: bal setsavepower_time 0x4d783c'),
    (0x4d78dc, 0x12000009, 'reset_poweroptions_timer: beqz s0: the screen light only for a non-zero third argument'),
    (0x4d78ec, 0x0411ffc1, 'reset_poweroptions_timer: bal setlight_time 0x4d77f4'),
)
PINYIN_PINS = (   # (address, stock word, what it proves)
    (0x5c7350, 0x3c1c0044, 'im_open_decoder prologue'), (0x5c7354, 0x279ccb80, 'im_open_decoder prologue'), (0x5c7358, 0x0399e021, 'im_open_decoder prologue'),
    (0x5c7534, 0x3c1c0044, 'im_close_decoder prologue'), (0x5c7538, 0x279cc99c, 'im_close_decoder prologue'), (0x5c753c, 0x0399e021, 'im_close_decoder prologue'),
    (0x5c760c, 0x3c1c0044, 'im_search prologue'), (0x5c7610, 0x279cc8c4, 'im_search prologue'), (0x5c7614, 0x0399e021, 'im_search prologue'),
    (0x5c76e8, 0x3c1c0044, 'im_reset_search prologue'), (0x5c76ec, 0x279cc7e8, 'im_reset_search prologue'), (0x5c76f0, 0x0399e021, 'im_reset_search prologue'),
    (0x5c7754, 0x3c1c0044, 'im_get_candidate prologue'), (0x5c7758, 0x279cc77c, 'im_get_candidate prologue'), (0x5c775c, 0x0399e021, 'im_get_candidate prologue'),
    (0x5c7824, 0x3c1c0044, 'im_get_fixed_len prologue'), (0x5c7828, 0x279cc6ac, 'im_get_fixed_len prologue'), (0x5c782c, 0x0399e021, 'im_get_fixed_len prologue'),
    (0x5c778c, 0x3c1c0044, 'im_get_spl_start_pos prologue'), (0x5c7790, 0x279cc744, 'im_get_spl_start_pos prologue'), (0x5c7794, 0x0399e021, 'im_get_spl_start_pos prologue'),
    (0x5c77c0, 0x3c1c0044, 'im_choose prologue'), (0x5c77c4, 0x279cc710, 'im_choose prologue'), (0x5c77c8, 0x0399e021, 'im_choose prologue'),
    (0x5c6834, 0x3c1c0044, 'MatrixSearch::get_predicts prologue'), (0x5c6838, 0x279cd69c, 'MatrixSearch::get_predicts prologue'), (0x5c683c, 0x0399e021, 'MatrixSearch::get_predicts prologue'),
    (0x5bffd4, 0x3c1c0044, 'DictList::get_splids_for_hanzi prologue'), (0x5bffd8, 0x279c3efc, 'DictList::get_splids_for_hanzi prologue'), (0x5bffdc, 0x0399e021, 'DictList::get_splids_for_hanzi prologue'),
    (0x5c01a4, 0x3c1c0044, 'DictList::get_lemma_id prologue'), (0x5c01a8, 0x279c3d2c, 'DictList::get_lemma_id prologue'), (0x5c01ac, 0x0399e021, 'DictList::get_lemma_id prologue'),
    (0x5c922c, 0x3c1c0044, 'SpellingTrie::get_spelling_str prologue'), (0x5c9230, 0x279caca4, 'SpellingTrie::get_spelling_str prologue'), (0x5c9234, 0x0399e021, 'SpellingTrie::get_spelling_str prologue'),
    (0xa00410, 0x00a0a360, 'GOT word of the engine pointer: the global MatrixSearch* at 0xa0a360 every im_* function loads'),
    (0x5c7384, 0x8c440000, 'im_open_decoder: lw a0, (v0): an existing object is destroyed before the new one'), (0x5c7594, 0xae000000, 'im_close_decoder: sw zero, (s0): the pointer is cleared'),
    (0x5c5740, 0x90860000, 'MatrixSearch::search: lbu a2, (a0): the first byte of the object is tested (inited_)'), (0x5c5128, 0x90820000, 'MatrixSearch::get_candidate: lbu v0, (a0): inited_'),
    (0x5c3094, 0x90830000, 'MatrixSearch::get_candidate_num: lbu v1, (a0): inited_'),
    (0x5c2ed0, 0xa2020000, 'MatrixSearch::init: sb v0, (s0): inited_ = 1 once the system dictionary and the user dictionary step are done'),
    (0x5c2ff8, 0xa2020000, 'MatrixSearch::init_fd: sb v0, (s0): inited_ = 1'),
    (0x5c2e00, 0x14a0000a, 'MatrixSearch::init: bnez a1: a NULL system dictionary path fails'), (0x5c2e2c, 0x10c0fff6, 'MatrixSearch::init: beqz a2: a NULL user dictionary path fails'),
)
JPEG_PINS = (   # (address, stock word, what it proves): the libjpeg 7 layout patch/pccover.c writes by offset, as stock's own decoder (0x5dd5ec) and encoder (0x5de554) do, and the error exit it borrows
    (0x5dbfe0, 0x3c1c0042, 'libjpeg error_exit prologue'), (0x5dbfe4, 0x279c7ef0, 'libjpeg error_exit prologue'), (0x5dbfe8, 0x0399e021, 'libjpeg error_exit prologue'),
    (0x5dbffc, 0x8c900000, 'error_exit: lw s0, 0(a0): cinfo->err'), (0x5dc000, 0x8e190008, 'error_exit: lw t9, 8(s0): err->output_message'),
    (0x5dc014, 0x8f99f868, 'error_exit: lw t9, GOT longjmp'), (0x5dc01c, 0x26040088, 'error_exit: addiu a0, s0, 0x88 (delay slot): longjmp(the jmp_buf that follows the 0x88 byte error manager, 1)'),
    (0x5dd6ec, 0x240601d8, 'decoder: jpeg_CreateDecompress structsize 0x1d8'), (0x5dd6f0, 0x24050046, 'decoder: jpeg_CreateDecompress version 70'),
    (0x5dd768, 0xafa20048, 'decoder: scale_num = 1 at cinfo + 0x30 (cinfo at sp + 0x18)'), (0x5dd774, 0xafa2004c, 'decoder: scale_denom at cinfo + 0x34'),
    (0x5dd790, 0x8fb30088, 'decoder: lw output_width from cinfo + 0x70'), (0x5dd798, 0x8fb2008c, 'decoder: lw output_height from cinfo + 0x74'),
    (0x5dd794, 0x8fb4003c, 'decoder: lw s4, 0x3c(sp): num_components at cinfo + 0x24'),
    (0x5de5ac, 0x240601a8, 'encoder: jpeg_CreateCompress structsize 0x1a8'), (0x5de5b4, 0x24050046, 'encoder: jpeg_CreateCompress version 70'),
    (0x5de654, 0xafb10034, 'encoder: image_width at cinfo + 0x1c'), (0x5de65c, 0xafb60038, 'encoder: image_height at cinfo + 0x20'),
    (0x5de668, 0xafb5003c, 'encoder: input_components at cinfo + 0x24'), (0x5de660, 0xafa20040, 'encoder: in_color_space at cinfo + 0x28'),
)
COVER_PINS = (   # (address, stock word, what it proves): stock's cover extraction as patch/covercache.c art_embedded / art_folder and patch/pccover.c pv_cover reproduce it (docs/modules/coverflow.md "Cover resampling")
    (0x5de680, 0x2405005a, 'the JPEG writer 0x5de554: jpeg_set_quality(cinfo, 90, 1): CV_QUALITY'),
    (0x5eaf00, 0x3c060010, 'toolsGetAlbumCover: taglib_album_picture(track, dst, 0x100000, 0x600000): a2'), (0x5eaf0c, 0x3c070060, 'toolsGetAlbumCover: a3 = 0x600000'),
    (0x5eaf24, 0x24030002, 'toolsGetAlbumCover: the result 2 (a JPEG) goes to the JPEG resize 0x5e03cc'), (0x5eafa8, 0x24030001, 'toolsGetAlbumCover: the result 1 (a PNG) goes to the PNG resize 0x5dfe98'),
    (0x757838, 0x706d742f, 'the string "/tmp/.tmp_picture" (libtag_c save_picturefile writes it, toolsGetAlbumCover reads and removes it)'), (0x75783c, 0x6d742e2f, '"/tmp/.tmp_picture"'),
    (0x757840, 0x69705f70, '"/tmp/.tmp_picture"'), (0x757844, 0x72757463, '"/tmp/.tmp_picture"'), (0x757848, 0x00000065, '"/tmp/.tmp_picture"'),
    (0x5de8cc, 0x2a820003, 'the JPEG loader 0x5de714: under three components goes to the scaled decode'), (0x5de8d4, 0x2a620401, 'the JPEG loader: a width over 1024 goes to the scaled decode'),
    (0x5de8e0, 0x2a420401, 'the JPEG loader: a height over 1024 goes to the scaled decode'),
    (0x5de344, 0x2a020401, 'the PNG loader 0x5de1a8: a width over 1024 is refused'), (0x5de350, 0x2a420401, 'the PNG loader: a height over 1024 is refused'),
    (0x5e0184, 0x24080008, 'the resize 0x5e00bc after a refused full decode: t0 = 8'), (0x5e01a0, 0x28421001, 'the scale: the longer side up to 4096 keeps t0 = 1'), (0x5e01a8, 0x2464fc00, 'the scale: a0 = side - 1024'),
    (0x5e01ac, 0x2463f800, 'the scale: v1 = side - 2048'), (0x5e01b0, 0x24070004, 'the scale: 4'), (0x5e01b4, 0x2c630801, 'the scale: 2048..4096 takes 4'), (0x5e01c0, 0x24070002, 'the scale: 2'),
    (0x5e01c4, 0x2c840401, 'the scale: 1024..2048 takes 2'), (0x5e01c8, 0x0044380a, 'the scale: movz a3, v0, a0'),
    (0x5e01e8, 0x0047182a, 'the fit: slt v1, width, height (a portrait goes to 0x5e02bc)'), (0x5e01f4, 0x0202182a, 'the landscape fit: slt v1, requested width, width'),
    (0x5e01f8, 0x1060003d, 'the landscape fit: a width not over the request goes to 0x5e02f0'), (0x5e0210, 0x46010043, 'the landscape fit: div.s f1 = width / requested width'),
    (0x5e021c, 0x46010003, 'the landscape fit: div.s f0 = height / f1'), (0x5e0220, 0x4600000d, 'the landscape fit: trunc.w.s'),
    (0x5e02bc, 0x1060000c, 'the portrait fit: a height not over the request goes to 0x5e02f0'), (0x5e02c0, 0x0050182a, 'the portrait fit: slt v1, width, requested width (delay slot)'),
    (0x5e02d4, 0x46010043, 'the portrait fit: div.s f1 = height / requested height'), (0x5e02e0, 0x46010003, 'the portrait fit: div.s f0 = width / f1'), (0x5e02e4, 0x4600000d, 'the portrait fit: trunc.w.s'),
    (0x5e02f0, 0x1060ffcd, 'a side exactly the request goes to the resize with the plain request (t x t)'), (0x5e02f4, 0x00f1182a, 'the other side under the request is kept as it is'), (0x5e02f8, 0x1060ffcb, 'a side equal: the resize'),
    (0x5eb760, 0x3c030010, 'toolsGetExternCover: a PNG file of up to 0x100000 bytes (the size, not the pixels)'), (0x5eb7bc, 0x3c030060, 'toolsGetExternCover: a JPEG file of up to 0x600000 bytes'),
    (0x5eb198, 0x9044000a, 'toolsGetExternCover: lbu a0, 0xa(v0): d_type'), (0x5eb19c, 0x24030008, 'toolsGetExternCover: DT_REG only'),
    (0x5eb660, 0x8f99f27c, 'toolsGetExternCover: a name that matches moves to the front: GOT _deque_push_front'), (0x5eb680, 0x26310200, 'toolsGetExternCover: the next of the nine names, 0x200 bytes on'), (0x5eb684, 0x1635ffa7, 'toolsGetExternCover: nine names (the loop ends at 0x1220)'),
    (0x7585f0, 0x646c6f66, '"folder.png"'), (0x7585f4, 0x702e7265, '"folder.png"'), (0x7585f8, 0x0000676e, '"folder.png"'),
    (0x758bf0, 0x65766f63, '"cover.png"'), (0x758bf4, 0x6e702e72, '"cover.png"'), (0x758bf8, 0x00000067, '"cover.png"'),
)
TAPE_PINS = (   # (address, stock word, what it proves): the Tape page invalidates a rectangle of its view (patch/tape.c tp_flush)
    (0x6691f0, 0x1000feea, 'widget_invalidate_force: b widget_invalidate (0x668d9c) with the rectangle it was given (a1 untouched)'),
    (0x668de4, 0x14a00011, 'widget_invalidate: bnez a1: a rectangle that is given is used as it is, in the widget\'s own coordinates (NULL: 0, 0, w, h)'),
    (0x668e14, 0x24060010, 'widget_invalidate: the rectangle is 16 bytes (rect_init, copied with memcpy 0x10): four 32 bit words x, y, w, h'),
)
LYRICS_PINS = (   # (address, stock word, what it proves): the stock lyric rows patch/lyrics.c reads (docs/modules/lyrics.md)
    (0x4e02e4, 0x3c1c0052, 'get_playtime prologue'), (0x4e02e8, 0x279c3bec, 'get_playtime prologue'), (0x4e02ec, 0x0399e021, 'get_playtime prologue'),
    (0x751c3c, 0x6f726373, 'the string "scroll_lrc" (the list the stock timers fill)'), (0x751c40, 0x6c5f6c6c, '"scroll_lrc"'), (0x751c44, 0x00006372, '"scroll_lrc"'),
    (0x751c80, 0x5f63726c, 'the string "lrc_time" (the int property of every lyric row)'), (0x751c84, 0x656d6974, '"lrc_time"'),
    (0x5384bc, 0x24451c80, 'the online row builder 0x537fec: widget_set_prop(row, "lrc_time", time)'),
    (0x538654, 0x26941c80, 'the online lyric timer 0x537fec: s4 = "lrc_time", the property it reads from each row'),
    (0x5385cc, 0x0320f809, 'the online lyric timer: jalr mclGetPlayStatus'), (0x5385e0, 0x0320f809, 'the online lyric timer: jalr get_playtime when the status is not 1 (stopped is time 0)'),
    (0x5386a8, 0x0320f809, 'the online lyric timer: jalr widget_get_prop(row, "lrc_time")'),
    (0x536e3c, 0x90626d30, 'the stock lyric row click handler 0x536e1c: lbu v0, 0x6d30(v1): it flips the lyric display flag (and refreshes the page), it does not seek'), (0x536e50, 0xa0626d30, 'the row click handler: sb v0, 0x6d30(v1) (in the delay slot of the refresh call)'),
    (0x4e0544, 0x3c1c0052, 'seek_time prologue (the tap-to-seek call; also pinned by PODCAST_PINS)'),
    (0x62e9f8, 0x24a5add8, 'label paint (the line_wrap branch): a1 = "spacer" (0x75add8), the style int that sets the row pitch'), (0x62ea04, 0x9615000c, 'label paint: lhu s5, 0xc(canvas) = the font size'),
    (0x62ea24, 0x02a29821, 'label paint: row pitch s3 = font size + style "spacer" (default 2): LY_LINE_H = LY_FONT + the style\'s spacer'),
    (0x650ebc, 0x1440ffcf, 'font_manager_get_font: a font name that cannot be loaded is retried with the default font name (the fallback of np_lyric_style when lyrics.ttf is missing); no per-glyph fallback'),
    (0x66aac0, 0x1040000d, 'widget_use_style: beqz widget_is_window_opened: the style is resolved (widget_update_style) only in an opened window, else only marked: the probe resolves its own (ly_probe_face)'),
    (0x6667a8, 0x10c00008, 'widget_update_style: beqz on the need_update_style bit: nothing to do once the style is resolved'),
    (0x676bb8, 0x24020002, 'window_base_on_event, EVT_WINDOW_WILL_OPEN: v0 = 2 (WINDOW_STAGE_CREATED) ...'), (0x676bc8, 0xae220094, '... stored as the window\'s stage'),
    (0x676bd4, 0x0411beff, 'window_base_on_event, EVT_WINDOW_WILL_OPEN: bal widget_update_style_recursive (every widget\'s style resolved, after the window theme is loaded): from stage 2 a measure is in the asked style'),
    # the idle lyrics page (patch/idlelyrics.c, docs/modules/idlelyrics.md) reads Now Playing's scroll_lrc rows while another window covers it: stock keeps rebuilding them
    (0x53cf68, 0x8c900024, 'Now Playing\'s 500 ms timer callback 0x53cf48 (player_timer_start 0x53c210): lw s0, 0x24(a0): the window it was registered with'), (0x53cf6c, 0x1200006e, 'the callback: beqz s0, end: only a callback without its window does nothing; no test of the top window before the next call'),
    (0x53cffc, 0x0411faad, 'the callback: bal show_player_face (0x53bab4) with a1 = 0 on every tick, before the Cover mode / playing_page test (0x53d008..) that only guards the idle countdown'),
    (0x53bb68, 0x92a20000, 'show_player_face: lbu autochange_refresh (0xa05a62; set by the main loop\'s song change 0x4ce8f8)'), (0x53bb6c, 0x14400006, 'show_player_face: a set autochange_refresh takes the full refresh'),
    (0x53bb74, 0x92820000, 'show_player_face: lbu force_refreshflag (0xa05a63)'), (0x53bb78, 0x104000e0, 'show_player_face: neither flag set: the light path, no row rebuild'),
    (0x53bed0, 0x0411f8db, 'show_player_face: bal 0x53a240, the lyric row builder, in the full refresh'), (0x53bee0, 0xa2800000, 'show_player_face: sb zero force_refreshflag after the refresh'), (0x53bee4, 0xa2a00000, 'show_player_face: sb zero autochange_refresh after the refresh'),
    (0x53a260, 0x24a51c3c, 'the row builder 0x53a240: a1 = "scroll_lrc", looked up recursively in the window it is given (the second lookup is "label_lyricmsg")'),
)
QUERY_PINS = (   # (address, stock word, what it proves): the first word after the prologue the trampolines resume at (the frame), and the sqlite3_exec calls that run the SQL
    (0x5ee788, 0x27bdff28, 'toolsQueryDbTable: addiu sp, sp, -0xd8 (the trampoline resumes here)'), (0x5ee7fc, 0x0320f809, 'toolsQueryDbTable: jalr sqlite3_exec(db, sql=a1, cb=a2)'),
    (0x5ee9b8, 0x27bdfe80, 'toolsQueryDbTableAndSort: addiu sp, sp, -0x180 (the trampoline resumes here)'), (0x5eea2c, 0x0320f809, 'toolsQueryDbTableAndSort: jalr sqlite3_exec(db, sql=a1, cb=a2)'),
    # The Daily Mix's own song query (patch/dailymix.c dm_rows, docs/modules/dailymix.md): stock's getAllMusic query (sort_first_alphabet 0x4ea0ac) with another SQL: the database path
    # string (0x745a34) and the song row callback (0x4e9058: a row of 18 columns, pushed into *tools_pdeq_directory) as it loads them, the call, and the callback's own prologue
    (0x4ea11c, 0x24c69058, 'sort_first_alphabet: a2 = the song row callback 0x4e9058'), (0x4ea120, 0x0320f809, 'sort_first_alphabet: jalr toolsQueryDbTable(db, sql, cb, 1)'),
    (0x4ea124, 0x24845a34, 'sort_first_alphabet: a0 = the database path string 0x745a34'),
    (0x4e9058, 0x3c1c0052, 'song row callback prologue'), (0x4e905c, 0x279cae78, 'song row callback prologue'), (0x4e9060, 0x0399e021, 'song row callback prologue'),
    (0x4e9068, 0x14a200d5, 'song row callback: bne a1, 0x12 (the column count): a row of any other width is skipped'),
    # The Queue page's cover map (patch/covercache.c cc_cmap_build, docs/modules/queue.md): getAllAlbum's own statement and row callback, run by the payload. getAllAlbum (0x4ea3c4) sprintf's the string
    # 0x74bad8 with "songtable" (0x74ba4c) and calls toolsQueryDbTable(db, sql, 0x4e93c8, 1); the callback (4 columns: id, album, songer, fileurl; an empty album is skipped) pushes one record into *tools_pdeq_directory
    (0x4ea428, 0x8f858020, 'getAllAlbum: a1 = GOT page 0x750000 (the SQL string)'), (0x4ea430, 0x24c6ba4c, 'getAllAlbum: a2 = "songtable" 0x74ba4c'),
    (0x4ea438, 0x24a5bad8, 'getAllAlbum: a1 = the SQL string 0x74bad8'), (0x4ea458, 0x24c693c8, 'getAllAlbum: a2 = the album row callback 0x4e93c8'),
    (0x4ea45c, 0x0320f809, 'getAllAlbum: jalr toolsQueryDbTable(db, sql, cb, 1)'),
    (0x4e93c8, 0x3c1c0052, 'album row callback prologue'), (0x4e93cc, 0x279cab08, 'album row callback prologue'), (0x4e93d0, 0x0399e021, 'album row callback prologue'),
    (0x4e93d4, 0x24020004, 'album row callback: v0 = 4'), (0x4e93d8, 0x14a20075, 'album row callback: bne a1, 4 (the column count): a row of any other width is skipped'),
    # The Favourites list and Saved (patch/pcmodel.c pq_filter, docs/modules/podcasts.md "Saved"): getAllFav runs sprintf(buf, "select * from %s", "myfav") and toolsQueryDbTable on it; the three myfav
    # wrappers the star button (manage_myfav 0x4ef884) uses are thin calls on the same table, keyed by filename / fileurl / the cue times of the record.
    (0x4ec45c, 0x3c1c0051, 'getAllFav prologue'), (0x4ec460, 0x279c7a74, 'getAllFav prologue'), (0x4ec464, 0x0399e021, 'getAllFav prologue'), (0x4ec4d0, 0x0320f809, 'getAllFav: jalr toolsQueryDbTable'),
    (0x4ee210, 0x3c1c0051, 'checkFavExist prologue'), (0x4ee214, 0x279c5cc0, 'checkFavExist prologue'), (0x4ee218, 0x0399e021, 'checkFavExist prologue'),
    (0x4ee234, 0x3c1c0051, 'addMyFav prologue'), (0x4ee238, 0x279c5c9c, 'addMyFav prologue'), (0x4ee23c, 0x0399e021, 'addMyFav prologue'),
    (0x4ede88, 0x3c1c0051, 'deleteMusicFromFav prologue'), (0x4ede8c, 0x279c6048, 'deleteMusicFromFav prologue'), (0x4ede90, 0x0399e021, 'deleteMusicFromFav prologue'),
)
SCAN_SITE = 0x5ea6a8
SCAN_PINS = (   # (address, stock word, what it proves)
    (0x5ea364, 0x3c1c0042, 'library folder lister prologue'), (0x5ea368, 0x279c9b6c, 'library folder lister prologue'), (0x5ea36c, 0x0399e021, 'library folder lister prologue'),
    (0x5ea69c, 0x8f85a708, 'folder lister: lw a1, GOT page 0x740000'), (0x5ea6a0, 0x02002025, 'folder lister: move a0, s0: the entry name'),
    (0x5ea6a4, 0x8f99f56c, 'folder lister: lw t9, GOT strcmp'), (SCAN_SITE, 0x0320f809, 'folder lister: jalr strcmp(name, ".")'),
    (0x5ea6ac, 0x24a53ed4, 'folder lister: addiu a1, a1, 0x3ed4 (delay slot): a1 = "."'), (0x5ea6b0, 0x1040ffd3, 'folder lister: beqz v0, 0x5ea600: a match goes back to readdir'),
)
# Battery Percentage (patch/battery.c bp_capacity, docs/modules/payload.md hook 8, docs/modules/battery.md "The percentage"): show_sysbar_face (0x544b48, the status bar's 1 s timer) calls
# get_battery_capacity (0x4e6dd8) at 0x5450f8 and drops the result; the capacity the fill uses is the global power_capacity (0xa059ec) the function leaves (the bucketed voltage, or the charging
# animation's +10), read at 0x545120 / 0x545154 / 0x54536c and by the pull-down's face (dropdown_showface 0x475c3c, on its own timer). The `jalr` becomes `jal bp_capacity` (the delay slot is a nop):
# stock's function first, then the gauge's percentage into power_capacity when Battery Percentage is on. Not reachable at boot (tools/reach.py).
BATTERY_SITE = 0x5450f8
BATTERY_PINS = (   # (address, stock word, what it proves)
    (0x544b48, 0x3c1c004c, 'show_sysbar_face prologue'), (0x544b4c, 0x279cf388, 'show_sysbar_face prologue'), (0x544b50, 0x0399e021, 'show_sysbar_face prologue'),
    (0x5450f0, 0x8fbc0010, 'show_sysbar_face: lw gp, 0x10(sp)'), (0x5450f4, 0x8f99be60, 'show_sysbar_face: lw t9, GOT get_battery_capacity'),
    (BATTERY_SITE, 0x0320f809, 'show_sysbar_face: jalr get_battery_capacity'), (0x5450fc, 0x00000000, 'show_sysbar_face: nop (the delay slot)'),
    (0x545100, 0x12600089, 'show_sysbar_face: beqz s3 (img_battery): the result is not read'), (0x545104, 0x8fbc0010, 'show_sysbar_face: lw gp, 0x10(sp) (the $gp is reloaded after the call)'),
    (0x545120, 0x8f90a9dc, 'show_sysbar_face: lw s0, GOT power_capacity'), (0x545154, 0x8e020000, 'show_sysbar_face: lw v0, (s0): the fill is power_capacity'),
    (0x54510c, 0x8f82a910, 'show_sysbar_face: lw v0, GOT 0xa059f8 (POWER_EXT)'), (0x545110, 0x24030001, 'show_sysbar_face: li v1, 1'), (0x54511c, 0x1443000d, 'show_sysbar_face: bne v0, v1: POWER_EXT != 1 goes to the low / normal test'),
    (0x545124, 0x8f83a964, 'show_sysbar_face: lw v1, GOT 0xa059f4 (POWER_USBSTATE)'), (0x545128, 0x8c640000, 'show_sysbar_face: lw a0, (v1)'),
    (0x54512c, 0x24030002, 'show_sysbar_face: li v1, 2'), (0x545130, 0x1483006c, 'show_sysbar_face: bne a0, v1: POWER_USBSTATE != 2 goes to the charging pictures'),
    (0x545134, 0x8f83a958, 'show_sysbar_face: lw v1, GOT 0xa05aa8 (POWER_FLAG)'), (0x545138, 0x80630000, 'show_sysbar_face: lb v1, (v1)'),
    (0x54513c, 0x1462006a, 'show_sysbar_face: bne v1, v0 (1): POWER_FLAG != 1 goes to the charging pictures'),
    (0x545144, 0x8f82a928, 'show_sysbar_face: lw v0, GOT 0x97cae8 (USBDAC_CHARGEFLAG)'), (0x545148, 0x8c420000, 'show_sysbar_face: lw v0, (v0)'),
    (0x54514c, 0x14400066,'show_sysbar_face: bnez v0: USBDAC_CHARGEFLAG != 0 goes to the charging pictures'),
    (0x545158, 0x1c40008b,'show_sysbar_face: bgtz v0: power_capacity > 0 is bar_power, else bar_lowpower'),
    (0x4e6dd8, 0x3c1c0052, 'get_battery_capacity prologue'), (0x4e6ddc, 0x279cd0f8, 'get_battery_capacity prologue'), (0x4e6de0, 0x0399e021, 'get_battery_capacity prologue'),
    (0x4e6e88, 0x8f90a9dc, 'get_battery_capacity: lw s0, GOT power_capacity (the global it leaves)'),
    (0x66d194, 0x8e020008, 'widget_resize: lw v0, 8(s0): widget_t.w'), (0x66d1a0, 0x8e03000c, 'widget_resize: lw v1, 0xc(s0): widget_t.h'),
    (0x66c428, 0x8e040044, 'widget_set_visible: lw a0, 0x44(s0): widget_t.parent, handed to widget_set_need_relayout_children'),
)
# Line Out pill (patch/lineout.c lo_set_text, docs/modules/payload.md hook 20, docs/modules/lineout.md): while Line Out is on (byte 0xa05aa7) show_sysbar_face (status bar timer) and dropdown_showface
# (the pull-down's own bar copy and timer) strcpy "LO" instead of the volume number into a buffer (s6) and join the number path at one call, widget_set_text_utf8(label_volume = s7, buffer): `lw t9, GOT` /
# `move a1, s6` / `jalr t9` / delay slot `move a0, s7`. Each jalr becomes `jal lo_set_text` (the delay slot stays stock's). Both functions set label_volume visible (`jalr widget_set_visible`, a1 = 1, a0 = s7)
# earlier in the same call, so the hook's hide wins. Not on the boot path (tools/reach.py: the same page-init dispatcher as the battery hook).
# Play history (patch/sbsrc.c sbs_play_record, docs/modules/payload.md hook 28, docs/modules/subsonic.md "Stock's play history"): on_wm_idle_status (0x4ce7d8) calls add_playrecord (0x4efb08) once per
# track start (mclGetPlayRecord set), its only caller. For a list play type (& 0xf000) that writes the queue record into recentplay and oftenplay of /mnt/data/database.db; a Subsonic stream's record
# holds the stream address with the login token. The `jalr` becomes `jal sbs_play_record` (the delay slot is a nop, the result is not read): a stream address is not written, everything else is stock's call.
PLAYREC_SITE = 0x4ce930
PLAYREC_PINS = (   # (address, stock word, what it proves)
    (0x4efb08, 0x3c1c0051, 'add_playrecord prologue'), (0x4efb0c, 0x279c43c8, 'add_playrecord prologue'), (0x4efb10, 0x0399e021, 'add_playrecord prologue'),
    (0x4ce928, 0x8fbc0010, 'on_wm_idle_status: lw gp, 0x10(sp)'), (0x4ce92c, 0x8f99b3e8, 'on_wm_idle_status: lw t9, GOT add_playrecord'),
    (PLAYREC_SITE, 0x0320f809, 'on_wm_idle_status: jalr add_playrecord'), (0x4ce934, 0x00000000, 'on_wm_idle_status: nop (the delay slot)'),
    (0x4ce938, 0x8fbc0010, 'on_wm_idle_status: lw gp, 0x10(sp) (the $gp is reloaded after the call; the result is not read)'),
)
LINEOUT_PINS = (   # (address, stock word, what it proves)
    (0x544f60, 0x8f82a950, 'show_sysbar_face: lw v0, GOT 0xa05aa7 (the Line Out byte)'), (0x544f64, 0x90420000, 'show_sysbar_face: lbu v0, (v0)'),
    (0x544f78, 0x8f99f324, 'show_sysbar_face: lw t9, GOT strcpy'), (0x544f7c, 0x0320f809, 'show_sysbar_face: jalr strcpy(buffer, "LO")'), (0x544f80, 0x24a546cc, 'show_sysbar_face: a1 = "LO" (0x7446cc)'),
    (0x544f88, 0x8f99a86c, 'show_sysbar_face: lw t9, GOT widget_set_text_utf8'), (0x544f8c, 0x02c02825, 'show_sysbar_face: move a1, s6 (the text)'),
    (0x544f90, 0x0320f809, 'show_sysbar_face: jalr widget_set_text_utf8'), (0x544f94, 0x02e02025, 'show_sysbar_face: move a0, s7 (label_volume; the delay slot)'),
    (0x544d90, 0x0320f809, 'show_sysbar_face: jalr widget_set_visible (a1 = 1)'), (0x544d94, 0x02e02025, 'show_sysbar_face: move a0, s7 (label_volume)'), (0x544d84, 0x24050001, 'show_sysbar_face: a1 = 1'),
    (0x475aa8, 0x8f82a950, 'dropdown_showface: lw v0, GOT 0xa05aa7 (the Line Out byte)'), (0x475aac, 0x90420000, 'dropdown_showface: lbu v0, (v0)'),
    (0x475ac0, 0x8f99f324, 'dropdown_showface: lw t9, GOT strcpy'), (0x475ac4, 0x0320f809, 'dropdown_showface: jalr strcpy(buffer, "LO")'), (0x475ac8, 0x24a546cc, 'dropdown_showface: a1 = "LO" (0x7446cc)'),
    (0x475ad0, 0x8f99a86c, 'dropdown_showface: lw t9, GOT widget_set_text_utf8'), (0x475ad4, 0x02c02825, 'dropdown_showface: move a1, s6 (the text)'),
    (0x475ad8, 0x0320f809, 'dropdown_showface: jalr widget_set_text_utf8'), (0x475adc, 0x02e02025, 'dropdown_showface: move a0, s7 (label_volume; the delay slot)'),
    (0x4758d8, 0x0320f809, 'dropdown_showface: jalr widget_set_visible (a1 = 1)'), (0x4758dc, 0x02e02025, 'dropdown_showface: move a0, s7 (label_volume)'), (0x4758cc, 0x24050001, 'dropdown_showface: a1 = 1'),
    (0x66f720, 0x3c1c0039, 'widget_set_text_utf8 prologue'),
)
# Apple-style Shuffle (patch/shuffle.c, docs/modules/shuffle.md, docs/modules/payload.md hooks 13-14). Stock never plays in mode 2: mclSetPlayMode (0x5d278c, the one function that stores the mode word
# 0xa0abe0 after boot, where initMclModule @0x5d1a6c stores 3) is hooked at its PIC prologue and maps a request for 2 to the payload's own shuffle flag with the stock mode 0; mclLoadPlayList
# (0x5d1f28, called by start_player @0x4e46e0, refresh_playqueue @0x4df59c and the boot resume in networkinit_thread @0x506374 / @0x506474) is hooked at its prologue and shuffles a queue just loaded
# while the flag is on. The mode is read raw (not through mclGetPlayMode) by mclNextSong @0x5d58fc, mclPrevSong @0x5d5748 and the next-index function @0x5d0edc, so those only ever see 0, 1, 3.
# Where the mode is displayed (or handed to a remote), stock's `jalr mclGetPlayMode` becomes `jal sh_display_mode`, which answers 2 while the flag is on: the same 19 call sites, each pinned with the
# `lw t9, GOT mclGetPlayMode` that loads it (0x8f99aab0). change_music @0x4e3d7c and autochange_updateplayqueue @0x4dfa08 keep the raw getter: they run the stock Shuffle branches for mode 2.
SETMODE, SETMODE_PROLOGUE = 0x5d278c, (0x3c1c0043, 0x279c1744, 0x0399e021)
LOADPL, LOADPL_PROLOGUE = 0x5d1f28, (0x3c1c0043, 0x279c1fa8, 0x0399e021)
# Song dates (patch/filetime.c, docs/modules/songs.md "Recently Added dates", payload hook 19): toolsGetFileCreateTime (0x5e4ac8) returns st_ctime from stat(), but st_atime
# (stat buffer at sp+0x18: atime +0x40, ctime +0x50) when the format byte 0xa0ac7c is 1 or 2 (exFAT, NTFS). The hook asks statx for the creation stamp first.
FILETIME, FILETIME_PROLOGUE = 0x5e4ac8, (0x3c1c0042, 0x279cf408, 0x0399e021)
FILETIME_PINS = (   # (address, stock word, what it proves)
    (FILETIME + 12, 0x27bdff38, 'toolsGetFileCreateTime: addiu sp, sp, -0xc8 (the trampoline resumes here)'), (0x5e4ae4, 0x14800008, 'toolsGetFileCreateTime: bnez a0 (a null path gives 0)'),
    (0x5e4b3c, 0x8f8280b4, 'toolsGetFileCreateTime: lw v0, GOT format byte (0xa10000 page)'), (0x5e4b40, 0x8fa30058, 'toolsGetFileCreateTime: lw v1, st_atime (sp+0x58)'),
    (0x5e4b44, 0x9050ac7c, 'toolsGetFileCreateTime: lbu s0, 0xa0ac7c (the format byte)'), (0x5e4b48, 0x8fa20068, 'toolsGetFileCreateTime: lw v0, st_ctime (sp+0x68)'),
    (0x5e4b58, 0x0070100b, 'toolsGetFileCreateTime: movn v0, v1, s0 (exFAT / NTFS take the access time)'),
)
# Library list hand-over (patch/libload.c, docs/modules/payload.md hook 29, docs/modules/libload.md): loadLocalClassList (0x4ee504) runs the class's query into *tools_pdeq_directory ($s0) and ends,
# for every class, in one tail at 0x4ee638: deque_clear(*dst); deque_assign(*dst, *tmp); deque_clear(*tmp); return deque_size(*dst), with dst ($s1) = &pdeq_showlist (0x4ee5b8, 0x4ee7a0),
# &pdeq_playlist (0x4ee634, class 0xf00b) or 0xa05fb4 (0x4ee7c8, the online classes 0xff23 and get_hifi_download_end). deque_assign copies every record and its strings while the query's rows
# are still held. The prologue becomes `j ll_load` (the old list of a local class is freed before the query); the `jalr deque_assign` becomes `jal ll_assign` (the two deque structs are exchanged,
# as libcstl's deque_swap does: CSTL_SWAP below). The jump tables (rodata, $gp-relative words) prove which classes end at the show list: LCL_TABLES.
LCL, LCL_PROLOGUE = 0x4ee504, (0x3c1c0051, 0x279c59cc, 0x0399e021)
LCL_ASSIGN_SITE = 0x4ee650
LCL_PINS = (   # (address, stock word, what it proves)
    (LCL + 12, 0x27bdffd8, 'loadLocalClassList: addiu sp, sp, -0x28 (the trampoline resumes here)'), (0x4ee530, 0x8f90b7d8, 'loadLocalClassList: lw s0, GOT tools_pdeq_directory'),
    (0x4ee5b8, 0x8f91ac08, 'loadLocalClassList: lw s1, GOT pdeq_showlist (an unknown class)'), (0x4ee7a0, 0x8f91ac08, 'loadLocalClassList: lw s1, GOT pdeq_showlist (the local classes)'),
    (0x4ee7c8, 0x8f91abfc, 'loadLocalClassList: lw s1, GOT 0xa05fb4 (the online classes)'), (0x4ee634, 0x8f91baa0, 'loadLocalClassList: lw s1, GOT pdeq_playlist (class 0xf00b)'),
    (0x4ee638, 0x8f99f494, 'loadLocalClassList tail: lw t9, GOT deque_clear'), (0x4ee63c, 0x0320f809, 'loadLocalClassList tail: jalr deque_clear'), (0x4ee640, 0x8e240000, 'loadLocalClassList tail: lw a0, (s1) (the destination)'),
    (0x4ee644, 0x8fbc0010, 'loadLocalClassList tail: lw gp'), (0x4ee648, 0x8e050000, 'loadLocalClassList tail: lw a1, (s0) (the query\'s rows)'), (0x4ee64c, 0x8f99f718, 'loadLocalClassList tail: lw t9, GOT deque_assign'),
    (LCL_ASSIGN_SITE, 0x0320f809, 'loadLocalClassList tail: jalr deque_assign (the site)'), (0x4ee654, 0x8e240000, 'loadLocalClassList tail: lw a0, (s1) (the delay slot)'), (0x4ee658, 0x8fbc0010, 'loadLocalClassList tail: lw gp (after the call)'),
    (0x4ee65c, 0x8f99f494, 'loadLocalClassList tail: lw t9, GOT deque_clear'), (0x4ee660, 0x0320f809, 'loadLocalClassList tail: jalr deque_clear'), (0x4ee664, 0x8e040000, 'loadLocalClassList tail: lw a0, (s0) (the rows are cleared)'),
)
# The two jump tables of loadLocalClassList as case addresses (word + $gp): classes 0xf002.. at 0x74c5b8 and 0xff01.. at 0x74c5e0. 0xf001 is the fall-through at 0x4ee5bc (getAllMusic).
# Every case but 0xf00b (0x4ee614: the playlists), 0xff23 (0x4ee7b4) and the unknown ones (0x4ee5a8) reaches 0x4ee79c / 0x4ee7a0, whose destination is the show list.
LCL_TABLES = (
    (0x74c5b8, (0x4ee5e4, 0x4ee6d0, 0x4ee6e8, 0x4ee714, 0x4ee72c, 0x4ee6a0, 0x4ee688, 0x4ee6b8, 0x4ee5fc, 0x4ee614)),
    (0x74c5e0, (0x4ee7cc, 0x4ee810) + (0x4ee5a8,) * 6 + (0x4ee760,) + (0x4ee5a8,) * 6 + (0x4ee83c, 0x4ee858, 0x4ee8b8, 0x4ee744, 0x4ee890) + (0x4ee5a8,) * 11 + (0x4ee78c, 0x4ee7a4, 0x4ee7ac, 0x4ee7b4, 0x4ee7ac)),
)
# The classes whose old list ll_load frees before the query: the local ones that end at the show list (LCL_TABLES). patch/libload.c ll_local names the same set.
LCL_LOCAL = tuple(range(0xf001, 0xf00b)) + (0xff01, 0xff02, 0xff09, 0xff10, 0xff11, 0xff12, 0xff13, 0xff14)
# Stock's slider page (docs/modules/peq.md "10-Band EQ"): its one caller is the All Playback Settings Equalizer row, a case of on_playsetback_onclick (`lw a0 "playset/equalizer_page"; b 0x4a0064` into the shared navigator_to
# call). The case's first two words become `j pod_eq_site; nop`: the stub opens our Equalizer page and resumes at the function's epilogue (0x4a0070). Not reachable at boot (a list click).
EQ_ROW = 0x4a0210
EQ_PINS = (   # (address, stock word, what it proves)
    (0x49fff4, 0x27bdff90, 'on_playsetback_onclick: addiu sp, sp, -0x70'), (0x4a0080, 0x8fbf006c, 'its epilogue reloads ra'), (0x4a0070, 0x8fb00060, 'its epilogue: lw s0, 0x60(sp)'), (0x4a0088, 0x27bd0070, 'its epilogue frees the frame'),
    (EQ_ROW, 0x8f84a708, 'Play Settings Equalizer row: lw a0, GOT 0x740000'), (EQ_ROW + 4, 0x1000ff93, 'its `b 0x4a0064` (the shared navigator_to call)'), (EQ_ROW + 8, 0x248474d4, 'its delay slot: a0 = "playset/equalizer_page"'),
)
NEXTALBUM_PINS = (   # (address, stock word, what it proves)
    (0x5d5800, 0x3c1c0043, 'mclNextSong prologue'), (0x5d5804, 0x279ce6d0, 'mclNextSong prologue'), (0x5d5808, 0x0399e021, 'mclNextSong prologue'),
    (0x5d580c, 0x27bdffd8, 'mclNextSong: addiu sp, sp, -0x28'),
    (0x5d5820, 0x00808825, 'mclNextSong: move s1, a0 (the automatic flag, read again at 0x5d59e0)'),
    (0x5d5910, 0x1040000f, 'mclNextSong: raw mode 0 (List play) takes the end test'),
    (0x5d5920, 0x8f99b79c, 'mclNextSong: the next song start (lw t9 mclStartPlayer; bal) the end test jumps to'), (0x5d5924, 0x0411fe76, 'mclNextSong: the next song start (lw t9 mclStartPlayer; bal) the end test jumps to'), (0x5d5928, 0x24100001, 'mclNextSong: the next song start (lw t9 mclStartPlayer; bal) the end test jumps to'),
    (0x5d5950, 0x8f92aa5c, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5954, 0x8f99f31c, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5958, 0x0320f809, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d595c, 0x8e440000, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5960, 0x8fbc0010, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5964, 0x2442ffff, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5968, 0x8f8380b4, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d596c, 0x8c65abdc, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5970, 0x00a2102b, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5974, 0x10400004, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5978, 0x00000000, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d597c, 0x24a50001, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5980, 0x1000ffe7, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'), (0x5d5984, 0xac65abdc, 'mclNextSong: the end test pos < size - 1 (a live read of the queue and the position), then pos + 1'),
    (0x5d5988, 0x8f8280b4, 'mclNextSong: the end branch (the hook site and the words after it)'), (0x5d598c, 0x8c43abd8, 'mclNextSong: the end branch (the hook site and the words after it)'), (0x5d5990, 0x24020001, 'mclNextSong: the end branch (the hook site and the words after it)'), (0x5d5994, 0x1462000f, 'mclNextSong: the end branch (the hook site and the words after it)'),
    (0x5d59d4, 0x8f99b408, 'mclNextSong: mclStop, then the automatic call stops, a manual one restarts the last song'), (0x5d59d8, 0x0411f29c, 'mclNextSong: mclStop, then the automatic call stops, a manual one restarts the last song'), (0x5d59dc, 0x00000000, 'mclNextSong: mclStop, then the automatic call stops, a manual one restarts the last song'), (0x5d59e0, 0x1220ffcf, 'mclNextSong: mclStop, then the automatic call stops, a manual one restarts the last song'), (0x5d59e4, 0x8fbc0010, 'mclNextSong: mclStop, then the automatic call stops, a manual one restarts the last song'),
    (0x4ee7c8, 0x8f91abfc, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7cc, 0x8f83b968, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7d0, 0x8f84aa68, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7d4, 0x8c650000, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7d8, 0x24030001, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7dc, 0x14a3000a, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7e0, 0x9082000a, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7e4, 0x8f99bac8, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7e8, 0x10400002, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7ec, 0x2484010d, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7f0, 0x00002025, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7f4, 0x0320f809, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7f8, 0x00000000, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee7fc, 0x3404ff01, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee800, 0x1000ff73, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'), (0x4ee804, 0x8fbc0010, 'loadLocalClassList 0xff01: the artist albums getter by ARTIST_TYPE'),
    (0x4ee80c, 0x8f99bacc, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee810, 0x8f84aa68, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee814, 0x8f99bad0, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee818, 0x9082000b, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee81c, 0x10400002, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee820, 0x2484020d, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee824, 0x00002025, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee828, 0x0411f33a, 'loadLocalClassList 0xff02: getAlbumByComposer'), (0x4ee82c, 0x00000000, 'loadLocalClassList 0xff02: getAlbumByComposer'),
    (0x4ee83c, 0x8f84aa68, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee840, 0x8f99b7ec, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee844, 0x90820009, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee848, 0x1040ffc1, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee84c, 0x2484000d, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee850, 0x1000ffbf, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'), (0x4ee854, 0x00002025, 'loadLocalClassList 0xff10: getMusicByAlbum(Unknown Album ? 0 : album)'),
    (0x4ee858, 0x8f83b968, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee85c, 0x8f84aa68, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee860, 0x8c650000, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee864, 0x24030001, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee868, 0x9082000a, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee86c, 0x14a30006, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee870, 0x90860008, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee874, 0x8f99b96c, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee878, 0x1040000b, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee87c, 0x2485010d, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee880, 0x10000009, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee884, 0x00002825, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'), (0x4ee888, 0x1000fffb, 'loadLocalClassList 0xff11: getMusicByAlbumAnd[Album]Songer by ARTIST_TYPE'),
    (0x4ee88c, 0x8f99b7dc, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee890, 0x8f84aa68, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee894, 0x8f99b7f0, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee898, 0x2485020d, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee89c, 0x9082000b, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee8a0, 0x1440fff7, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee8a4, 0x90860008, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee8a8, 0x0320f809, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'), (0x4ee8ac, 0x2484000d, 'loadLocalClassList 0xff14: getMusicByAlbumAndComposer'),
    (0x4ee968, 0x8e470024, 'loadAlbumList: the album-artist field +0x24 (ARTIST_TYPE 1)'),
    (0x4ee9b4, 0x8e470018, 'loadAlbumList: the artist field +0x18 (else)'),
    (0x4ee9f4, 0x8e470020, 'loadAlbumList: the composer field +0x20'),
    (0x4eb0e4, 0x3c1c0052, 'getAlbumByAlbumArtist prologue'), (0x4eb0e8, 0x279c8dec, 'getAlbumByAlbumArtist prologue'), (0x4eb0ec, 0x0399e021, 'getAlbumByAlbumArtist prologue'),
    (0x4eaccc, 0x3c1c0052, 'getAlbumByArtist prologue'), (0x4eacd0, 0x279c9204, 'getAlbumByArtist prologue'), (0x4eacd4, 0x0399e021, 'getAlbumByArtist prologue'),
    (0x4eb514, 0x3c1c0052, 'getAlbumByComposer prologue'), (0x4eb518, 0x279c89bc, 'getAlbumByComposer prologue'), (0x4eb51c, 0x0399e021, 'getAlbumByComposer prologue'),
    (0x4ed2d4, 0x3c1c0051, 'getMusicByAlbumAndComposer prologue'), (0x4ed2d8, 0x279c6bfc, 'getMusicByAlbumAndComposer prologue'), (0x4ed2dc, 0x0399e021, 'getMusicByAlbumAndComposer prologue'),
    (0x4ed008, 0x3c1c0051, 'getMusicByAlbumAndAlbumSonger prologue'), (0x4ed00c, 0x279c6ec8, 'getMusicByAlbumAndAlbumSonger prologue'), (0x4ed010, 0x0399e021, 'getMusicByAlbumAndAlbumSonger prologue'),
    (0x4ecd3c, 0x3c1c0051, 'getMusicByAlbumAndSonger prologue'), (0x4ecd40, 0x279c7194, 'getMusicByAlbumAndSonger prologue'), (0x4ecd44, 0x0399e021, 'getMusicByAlbumAndSonger prologue'),
    (0x4ecb5c, 0x3c1c0051, 'getMusicByAlbum prologue'), (0x4ecb60, 0x279c7374, 'getMusicByAlbum prologue'), (0x4ecb64, 0x0399e021, 'getMusicByAlbum prologue'),
)
CLEAR_SITE = 0x5089e4   # dmr_serverstart: `jalr deque_clear` of the playing queue (delay slot lw a0, ($v0)); jal sh_clear_queue takes the payload lock around it
MODE_SITES = (   # (the jalr mclGetPlayMode, the lw t9 that loads it)
    (0x47a3fc, 0x47a3f8), (0x47a530, 0x47a51c), (0x49fb90, 0x49fb68), (0x49fd04, 0x49fcf8), (0x49fd58, 0x49fd4c), (0x49fdac, 0x49fda0), (0x49fe04, 0x49fdf4), (0x49fe7c, 0x49fe78),
    (0x4d8720, 0x4d871c), (0x4f014c, 0x4f013c), (0x4f0164, 0x4f0160), (0x4f017c, 0x4f0178), (0x4f09d8, 0x4f09d4), (0x4f0a30, 0x4f0a2c), (0x4f0a50, 0x4f0a4c), (0x50ecf8, 0x50ece8),
    (0x50ee34, 0x50ee30), (0x5398cc, 0x5398c8), (0x53b62c, 0x53b614))
SHUFFLE_PINS = (   # (address, stock word, what it proves)
    (SETMODE + 12, 0x27bdffe0, 'mclSetPlayMode: addiu sp, sp, -0x20 (the trampoline resumes here)'), (0x5d27b0, 0xac44abe0, 'mclSetPlayMode: sw a0, mode word 0xa0abe0'),
    (0x5d27b8, 0x8c45abd0, 'mclSetPlayMode: lw a1, gapless state 0xa0abd0'), (0x5d27bc, 0x14a30013, 'mclSetPlayMode: a state other than 1 skips the preload close'),
    (0x5d27c4, 0x10800011, 'mclSetPlayMode: mode 0 skips it'), (0x5d27d4, 0x1082000c, 'mclSetPlayMode: mode 3 skips it'), (0x5d27dc, 0x8c44abec, 'mclSetPlayMode: lw a0, the player socket 0xa0abec'),
    # mclSetGaplessMode(g) (pod_clear_upnext closes an open preload with it): stores the byte, and for 0 with a preload open (state 1) sends {mcl-closegapless} and stores -1
    (0x5d28cc, 0x14800012, 'mclSetGaplessMode: bnez a0 (the close is for 0 only)'), (0x5d28d0, 0xa044ab89, 'mclSetGaplessMode: sb a0, 0xa0ab89 (the setting)'),
    (0x5d28dc, 0x8c44abd0, 'mclSetGaplessMode: lw a0, 0xa0abd0 (the preload state)'), (0x5d28e0, 0x1483000d, 'mclSetGaplessMode: bne a0, 1 (only an open preload is closed)'),
    (0x5d290c, 0x24a564f8, 'mclSetGaplessMode: a1 = "{mcl-closegapless\\null}"'), (0x5d2914, 0xae02abd0, 'mclSetGaplessMode: sw -1, 0xa0abd0 (the preload state)'),
    (0x5d28ac, 0x3c1c0043, 'mclSetGaplessMode prologue'),
    (0x5d27f8, 0x0320f809, 'mclSetPlayMode: jalr send("{mcl-closegapless}")'), (0x5d2804, 0xae02abd0, 'mclSetPlayMode: sw -1, gapless state'),
    (LOADPL + 12, 0x27bdffd0, 'mclLoadPlayList: addiu sp, sp, -0x30 (the trampoline resumes here)'), (0x5d1f60, 0x8f90aa5c, 'mclLoadPlayList: lw s0, GOT play queue 0xa0394c'),
    (0x5d1f8c, 0xac52abdc, 'mclLoadPlayList: sw a1, play position 0xa0abdc'), (0x5d1f9c, 0xac51abd8, 'mclLoadPlayList: sw a2, class'),
    (0x4e46dc, 0x8f99b8b8, 'start_player: lw t9, GOT mclLoadPlayList'), (0x4e46e0, 0x0320f809, 'start_player: jalr mclLoadPlayList(queue, index, class)'),
    (0x5d58fc, 0x8c42abe0, 'mclNextSong: lw v0, mode word (raw)'), (0x5d5900, 0x10430047, 'mclNextSong: mode 2 branches to the unplayed pool 0x5d5a20'),
    (0x5d5748, 0x8c42abe0, 'mclPrevSong: lw v0, mode word (raw)'), (0x5d0edc, 0x8c42abe0, 'next-index function 0x5d0ea4: lw v0, mode word (raw)'),
    (0x5d3638, 0x03e00008, 'mclGetPlayMode: jr ra (the raw getter is not hooked)'), (0x5d363c, 0x8c42abe0, 'mclGetPlayMode: lw v0, mode word'),
    (0x5d42d8, 0x3c1c0043, 'mclSetPlayPos prologue'), (0x5d42ec, 0xac44abdc, 'mclSetPlayPos: sw a0, play position 0xa0abdc'),
    (0x5089dc, 0x8f82aa5c, 'dmr_serverstart: lw v0, GOT play queue 0xa0394c'), (0x5089e0, 0x8f99f494, 'dmr_serverstart: lw t9, GOT deque_clear'),
    # the DLNA renderer service flag (Queue page Clear and the queue insert of Play Next / Play After are off while it is 1): dlna_service_running reads it, dmr_serverstart sets it to 1 right after dmrStartService returns (UI-thread timer), dlna_servicestop clears it after dmrStopService
    (0x507bf8, 0x8f82bd30, 'dlna_service_running: lw v0, GOT dmr_serverflag 0xa06020'), (0x507bfc, 0x8c420000, 'dlna_service_running: lw v0, (dmr_serverflag)'), (0x507c00, 0x38420001, 'dlna_service_running: xori v0, dmr_serverflag, 1 (== 1)'),
    (0x5084a0, 0xae220000, 'dmr_serverstart: sw v0 (=1), (s1): the flag is set after dmrStartService'), (0x507a78, 0xae000000, 'dlna_servicestop: sw zero, (s0): the flag is cleared after dmrStopService'),
    # the readers of the Gapless byte / preload state the one cancel helper (patch/shuffle.c cancel_preload) relies on, and the setter's send
    (0x5d2908, 0x0320f809, 'mclSetGaplessMode: jalr send("{mcl-closegapless}")'),
    (0x5d583c, 0x9042ab89, 'mclNextSong: lbu v0, Gapless byte (0 takes the queue path)'), (0x5d6338, 0x8c63abd0, 'mclAutoChange: lw v1, preload state (a preload is started only at 0)'),
    (CLEAR_SITE, 0x0320f809, 'dmr_serverstart: jalr deque_clear(*queue)'), (CLEAR_SITE + 4, 0x8c440000, 'dmr_serverstart: delay slot lw a0, (v0)'),
) + tuple(p for a, l in MODE_SITES for p in ((a, 0x0320f809, f'jalr mclGetPlayMode {a:#x}'), (l, 0x8f99aab0, f'lw t9, GOT mclGetPlayMode (for {a:#x})')))
# Official firmware over the mod (docs/modules/version.md): update_firmware (0x4e0f10) refuses a package whose line-2 version strcmp-equals the "V2.1" literal (0x74773c), which an official
# V2.1 package is. Its compare (the addiu at 0x4e1124, a1 = literal) is pointed at the string "about_version" (0x74772c) instead: no package tag is that. The literal stays "V2.1" for the
# online check (check_otginfo), the download page and the About row. Not on the boot path (tools/reach.py).
UPDATE_SITE, UPDATE_STOCK, UPDATE_NEW = 0x4e1124, 0x24a5773c, 0x24a5772c
UPDATE_PINS = (   # (address, stock word, what it proves)
    (0x4e1114, 0x8f85a708, 'update_firmware: lw a1, GOT page 0x740000'), (0x4e1118, 0x02802025, 'update_firmware: move a0, s4 (the package version, line 2)'),
    (0x4e1120, 0x0320f809, 'update_firmware: jalr strcmp'), (UPDATE_SITE, UPDATE_STOCK, 'update_firmware: addiu a1, a1, 0x773c: a1 = "V2.1"'),
    (0x4e1128, 0x14400007, 'update_firmware: bnez v0: different version goes on to the install'),
    (0x74773c, 0x312e3256, 'the literal "V2.1"'), (0x747738, 0x0000006e, 'the end of "about_version": "n", NUL, padding'),
    (0x74772c, 0x756f6261, 'the string "about_version" ("abou"): the compare\'s new operand, a text no package tag equals'),
)
# Software Update (patch/update.c, docs/modules/update.md): the TF card update's own click handler on systemset/fwupdate_page (the "listitem_sd" row, bound by the page init's widget walk, @0x4a6d10..): called, not hooked. It is
# self-contained and ignores its arguments: the confirm dialog (msg_confirmupdate), check_updatefw_exist("/mnt/mmc", "/mnt/mmc/update.bin"), then navigator_to("dialog/cardupdate_dialog") (whose init stops the player and
# starts the flash thread; the codes of check_updatefw_exist answer with the stock low-battery and not-found messages). The payload calls it on the UI thread from a click handler, as stock's event loop does.
TF_UPDATE = 0x4a7160
TFUPDATE_PINS = (   # (address, stock word, what it proves)
    (TF_UPDATE, 0x3c1c0056, 'TF card update handler prologue'), (TF_UPDATE + 4, 0x279ccd70, 'TF card update handler prologue'), (TF_UPDATE + 8, 0x0399e021, 'TF card update handler prologue'),
    (0x4a71b8, 0x24847f44, 'TF card update: a0 = "msg_confirmupdate" (getFormatString)'), (0x4a71cc, 0x0320f809, 'TF card update: jalr navigator_to_with_context (the modal confirm)'),
    (0x4a71d0, 0x24844570, 'TF card update: a0 = "dialog/confirminfo_dialog"'), (0x4a71d8, 0x14430029, 'TF card update: bne v0, 0xa: only Yes goes on'),
    (0x4a71ec, 0x24a53ed8, 'TF card update: a1 = "/mnt/mmc/update.bin"'), (0x4a71f0, 0x0320f809, 'TF card update: jalr check_updatefw_exist'), (0x4a71f4, 0x24844bd0, 'TF card update: a0 = "/mnt/mmc"'),
    (0x4a7208, 0x0320f809, 'TF card update: jalr navigator_to'), (0x4a720c, 0x24847e00, 'TF card update: a0 = "dialog/cardupdate_dialog"'),
    (0x4a6cf4, 0x24a57e80, 'widget walk: a1 = "listitem_sd"'), (0x4a6d10, 0x8f86add4, 'widget walk: lw a2, GOT page 0x4a0000'), (0x4a6d14, 0x1000ffde, 'widget walk: b 0x4a6c90 (widget_on EVT_CLICK)'),
    (0x4a6d18, 0x24c67160, 'widget walk: a2 = 0x4a7160 (the delay slot): the row\'s click handler is the one called here'),
)
PLAYLIST_IMPORT, PLAYLIST_EXPORT = 0x53dedc, 0x53dd34
PLAYLIST_PINS = (   # (address, stock word, what it proves)
    (PLAYLIST_IMPORT, 0x3c1c004c, 'import click handler prologue'), (PLAYLIST_IMPORT + 4, 0x279c5ff4, 'import click handler prologue'),
    (PLAYLIST_IMPORT + 8, 0x0399e021, 'import click handler prologue'),
    (PLAYLIST_EXPORT, 0x3c1c004c, 'export click handler prologue'), (PLAYLIST_EXPORT + 4, 0x279c619c, 'export click handler prologue'),
    (PLAYLIST_EXPORT + 8, 0x0399e021, 'export click handler prologue'),
    (0x53df64, 0x8f99c2a4, 'import: lw importPlayList from the GOT'), (0x53df6c, 0x0320f809, 'import: jalr importPlayList'),
    (0x53ddc4, 0x8f99c2a0, 'export: lw exportPlayList from the GOT'), (0x53dde8, 0x0320f809, 'export: jalr exportPlayList'),
    (0x4eeca8, 0x3c1c0051, 'createPlayListItem prologue'), (0x4eecac, 0x279c5228, 'createPlayListItem prologue'), (0x4eecb0, 0x0399e021, 'createPlayListItem prologue'),
    (0x4ee184, 0x3c1c0051, 'getPlayListMaxId prologue'), (0x4ee188, 0x279c5d4c, 'getPlayListMaxId prologue'), (0x4ee18c, 0x0399e021, 'getPlayListMaxId prologue'),
    (0x4ee1a8, 0x3c1c0051, 'checkPlayListExist prologue'), (0x4ee1ac, 0x279c5d28, 'checkPlayListExist prologue'), (0x4ee1b0, 0x0399e021, 'checkPlayListExist prologue'),
    (0x4ee1cc, 0x3c1c0051, 'addPlayList prologue'), (0x4ee1d0, 0x279c5d04, 'addPlayList prologue'), (0x4ee1d4, 0x0399e021, 'addPlayList prologue'),
    (0x4db34c, 0x04114b96, 'batch_add_file (class 0xf00b): bal checkPlayListExist(rec, playlist id)'), (0x4db360, 0x04114b88, 'batch_add_file: bal getPlayListMaxId'),
    (0x4db380, 0x24030064, 'batch_add_file: v1 = 100'), (0x4db384, 0x2a640064, 'batch_add_file: slti a0, max, 100'), (0x4db38c, 0x0264180a, 'batch_add_file: movz v1, max, a0 (max(100, max))'),
    (0x4db3a4, 0xac430000, 'batch_add_file: rec.id (REC_ID) = max(100, max) + 1'), (0x4db3c0, 0xac430040, 'batch_add_file: rec.cd_num (REC_DISC) = the playlist id'),
    (0x4db3d0, 0x8f99b810, 'batch_add_file: lw addPlayList from the GOT (the delay slot of the jump to 0x4daff8)'), (0x4daff8, 0x0320f809, 'batch_add_file: jalr addPlayList(rec)'),
    # Delete (docs/modules/playlists.md "Delete"): the stock handler 0x53dbcc (mirrored by patch/playlists.c pl_on_delete) asks with the confirm dialog (Yes = 0xa), then calls
    # batch_delete_file(*0x97cad4 = 0xf00b, *pdeq_playlist, *0xa045e0, 0, 0); the class's case in batch_delete_file's jump table 0x74b7b0 (0xf00b is the ninth word) is the loop
    # that runs deletePlaylist and deleteAllMusicByPlaylist on the id (the record's first word) of every selected row
    (0x53dcc0, 0x2403000a, 'delete handler: v1 = 0xa, the confirm dialog\'s Yes'), (0x53dcc4, 0x1443ffe6, 'delete handler: bne v0, v1: anything but Yes ends it'),
    (0x53dcd0, 0x00003825, 'delete handler: a3 = 0'), (0x53dcd4, 0xafa00010, 'delete handler: delete_file (the 5th argument) = 0'),
    (0x53dcf0, 0x0320f809, 'delete handler: jalr batch_delete_file (a0 = the browsing class *0x97cad4)'),
    (0x74b7d0, 0xffade414, 'batch_delete_file jump table: the class 0xf00b word (+ gp 0xa03ed0 = 0x4e22e4, the playlist loop\'s test)'),
    # Clean Up Playlist (patch/songops.c so_relink / so_clean, from a playlist's "..." card, patch/songs.c sg_clean; docs/modules/playlists.md). A playlist's songs are read with
    # `select * from %s where id > 100 and cd_num=%d` (getMusicByPlayList), so a record's id (column 0, the row callback's atoi into +0) is its row's own id in the `playlist` table.
    # toolsUpdateDbTable(db, sql) opens the shared handle and runs sqlite3_exec(sql, no callback); toolsDeleteItemById(table, db, id) runs `delete from %s where id=%d`
    (0x4ede0c, 0x24a5c510, 'getMusicByPlayList: a1 = "select * from %s where id > 100 and cd_num=%d" 0x74c510'),
    (0x5eefb0, 0x3c1c0041, 'toolsUpdateDbTable prologue'), (0x5eefb4, 0x279c4f20, 'toolsUpdateDbTable prologue'), (0x5eefb8, 0x0399e021, 'toolsUpdateDbTable prologue'),
    (0x5ef008, 0x0320f809, 'toolsUpdateDbTable: jalr sqlite3_exec(db handle, sql = the second argument, 0, 0, &err)'),
    (0x5ef370, 0x3c1c0041, 'toolsDeleteItemById prologue'), (0x5ef374, 0x279c4b60, 'toolsDeleteItemById prologue'), (0x5ef378, 0x0399e021, 'toolsDeleteItemById prologue'),
    (0x5ef3f8, 0x24c67ec0, 'toolsDeleteItemById: a2 = "delete from %s where id=%d" 0x757ec0'), (0x5ef418, 0x0320f809, 'toolsDeleteItemById: jalr sqlite3_exec'),
    (0x4edfc4, 0x0320f809, 'deletePlaylist: jalr toolsDeleteItemById("playlist", the database path, id): stock\'s own use on this table'),
    (0x4e22b0, 0x04112f39, 'batch_delete_file, class 0xf00b loop: bal deletePlaylist 0x4edf98'), (0x4e22d4, 0x04112f41, 'batch_delete_file, class 0xf00b loop: bal deleteAllMusicByPlaylist 0x4edfdc'),
)
PICKER_PINS = (
    (0x4da7dc, 0x3c1c0053, 'batch_add_file prologue'), (0x4da7e0, 0x279c96f4, 'batch_add_file prologue'), (0x4da7e4, 0x0399e021, 'batch_add_file prologue'),
    (0x53d4b8, 0x3405f00b, 'picker row handler: a1 = 0xf00b (the playlist class), a0 = the context\'s class'), (0x53d4d4, 0x0320f809, 'picker row handler: jalr batch_add_file'),
    (0x53d4d8, 0xafa20010, 'picker row handler: the playlist id (REC_DISC of the row) is the 5th argument'),
    (0x5281c8, 0x3405f00a, 'stock Add button, Favourites: a1 = 0xf00a'), (0x5281cc, 0xafa00010, 'stock Add button, Favourites: the 5th argument is 0'),
    (0x5281d4, 0x8f99c0f4, 'stock Add button, Favourites: t9 = batch_add_file (GOT)'), (0x5281e8, 0x0320f809, 'stock Add button, Favourites: jalr batch_add_file'),
    (0x5281ec, 0x8c440000, 'stock Add button, Favourites: a0 = g_class_type'),
    (0x52822c, 0x24840e48, 'stock Add button, Favourites: msg_addfavsuccess'),
)
# ---- List gestures (patch/scroll.c, docs/architecture.md "List gestures") --------------------------------------------
# Not a code hook: widget_on_event_before_children (0x666c34) calls vtable[0x98] of a widget with every pointer event
# before its children see it, and g_scroll_view_vtable's slot is zero in stock (a no-op). The build writes
# m1plus_scroll_event into that one data word. The stock functions and fields the payload relies on are pinned below.
SCROLL_VTABLE = 0x97a298            # g_scroll_view_vtable (.dynsym)
SCROLL_SLOT = SCROLL_VTABLE + 0x98  # on_event_before_children: 0 in stock
# (address, stock word, what it proves). Vtable words are data, the rest instructions.
SCROLL_PINS = (
    (SCROLL_VTABLE, 0x118, 'scroll_view_t size'), (SCROLL_VTABLE + 0x14, 0x97c0d8, 'parent vtable (widget)'),
    (SCROLL_VTABLE + 0x1c, 0x6113c4, 'create = scroll_view_create'), (SCROLL_VTABLE + 0x94, 0x610724, 'on_event = scroll_view_on_event'),
    (SCROLL_SLOT, 0, 'on_event_before_children is empty'), (SCROLL_SLOT + 4, 0, 'the next slot is empty'),
    (0x666c44, 0x8c820070, 'widget_on_event_before_children: lw v0, 0x70(a0) (vt)'),
    (0x666c50, 0x8c590098, 'widget_on_event_before_children: lw t9, 0x98(vt)'), (0x666c5c, 0x03200008, 'widget_on_event_before_children: jr t9'),
    (0x67131c, 0x0411d645, 'widget_on_pointer_down: bal widget_on_event_before_children'),
    (0x671324, 0x10510041, 'widget_on_pointer_down: RET_STOP ends the DOWN'),
    (0x67169c, 0x0411d565, 'widget_on_pointer_move: bal widget_on_event_before_children'),
    (0x671924, 0x0411d4c3, 'widget_on_pointer_up: bal widget_on_event_before_children (before the children @0x671990)'),
    (0x66cf2c, 0x8c590094, 'widget_dispatch: lw t9, 0x94(vt) (on_event)'),
    (0x66e0bc, 0x8c90004c, 'widget_dispatch_event_to_target_recursive starts at the grab widget'),
    (0x66e0c8, 0x8c900048, 'and then at the target'),
    (0x610724, 0x3c1c003f, 'scroll_view_on_event prologue'), (0x610728, 0x279c37ac, 'scroll_view_on_event prologue'),
    (0x61072c, 0x0399e021, 'scroll_view_on_event prologue'),
    (0x61083c, 0xa61200a0, 'on_event DOWN: sh 1, 0xa0 (pressed = 1, dragged = 0)'),
    (0x61086c, 0xae020098, 'on_event DOWN: down x'), (0x61087c, 0xae02009c, 'on_event DOWN: down y'),
    (0x6108c4, 0x920200a0, 'on_event UP: lbu pressed'), (0x610c34, 0xa20200a1, 'on_event MOVE: sb dragged = 1'),
    (0x610680, 0x90830090, 'is_dragged: xslidable'), (0x610688, 0x90820091, 'is_dragged: yslidable'),
    (0x610694, 0x8c820098, 'is_dragged: down x'), (0x61069c, 0x8c85009c, 'is_dragged: down y'),
    (0x6106cc, 0x90820092, 'is_dragged: snap_to_page'), (0x6106e0, 0x2863000a, 'is_dragged: threshold 10'),
    (0x610548, 0xae0400e8, 'scroll_view_scroll_to: wa = the new animator'),
    (0x6101b8, 0x3c1c003f, 'scroll end handler prologue'), (0x6101bc, 0x279c3d18, 'scroll end handler prologue'),
    (0x6101c0, 0x0399e021, 'scroll end handler prologue'), (0x610208, 0xae2000e8, 'scroll end handler: wa = 0'),
    (0x673114, 0x8e020028, 'widget_animator_start: lw state'), (0x673118, 0x24030001, 'widget_animator_start: 1 = running'),
    (0x673258, 0x8e040004, 'widget_animator_stop: lw widget (@4)'),
    (0x6735d0, 0x8c830048, 'widget_animator_destroy: lw destroy flag (@0x48)'),
)
FOLDER_PINS = (   # (address, stock word, what it proves)
    (0x4db978, 0x3c1c0053, 'folder_enter prologue'), (0x4db97c, 0x279c8558, 'folder_enter prologue'), (0x4db980, 0x0399e021, 'folder_enter prologue'),
    (0x4db9b4, 0x04810002, 'folder_enter: bgez a0 (an index below 0 ...)'), (0x4db9bc, 0xae400000, '... clears the layer: the root list is loaded again'),
    (0x4dbbe8, 0x24020004, 'folder_enter: a record of type 4 (a folder) ...'), (0x4dbbec, 0x8e300034, '... type = record + 0x34'), (0x4dbbf0, 0x16020068, '... is entered (bne to the type 1 / 8 tests otherwise)'),
    (0x4dbd94, 0x16150049, 'folder_enter: type 1 (a playlist file) is parsed, any other type goes on'), (0x4dbd98, 0x3a020008, 'folder_enter: xori 8'),
    (0x4dbec0, 0x02a2800b, 'folder_enter: movn: the return value is 1 unless the type is 8, which returns 8 (an audio file: the caller plays it)'),
    (0x4dbecc, 0x3c1c0053, 'folder_back prologue'), (0x4dbed0, 0x279c8004, 'folder_back prologue'), (0x4dbed4, 0x0399e021, 'folder_back prologue'),
    (0x4dbedc, 0x8f83b81c, 'folder_back: v1 = &layer (GOT 0xa0554c, FOLDER_LAYER)'),
    (0x4dbefc, 0x2442ffff, 'folder_back: layer - 1'), (0x4dbf00, 0x1c40000c, 'folder_back: still above 0: one level up'), (0x4dbf14, 0x00001025, 'folder_back: otherwise clear_foldervariate, and 0 is returned (the page closes)'),
    (0x4dbf68, 0x8f84b828, 'folder_back: a0 = the title buffer (GOT 0xa0533c, FOLDER_TITLE)'), (0x4dbfc8, 0x24020001, 'folder_back: 1 is returned for the root list'),
    (0x4dbdbc, 0x8f84b820, 'folder_enter: a0 = the m3u path buffer (GOT 0xa0483c, FOLDER_M3U)'),
    (0x4db7ec, 0x3c1c0053, 'folder_reload prologue'), (0x4db7f0, 0x279c86e4, 'folder_reload prologue'), (0x4db7f4, 0x0399e021, 'folder_reload prologue'),
    (0x4db810, 0x28420002, 'folder_reload: layer < 2 loads the root list'),
    (0x532b60, 0x8f93ae70, 'the stock folder row: lw s3, GOT foldercover_flag (FOLDER_COVER, 0xa05a67), the flag that shows /mnt/mmc/.downpic/fd_<md5>.jpg in place of the icon'),
    (0x5329d8, 0x3c1c004d, 'is_folderplaying prologue'), (0x5329dc, 0x279c14f8, 'is_folderplaying prologue'), (0x5329e0, 0x0399e021, 'is_folderplaying prologue'),
    (0x532b94, 0x8e020034, 'the stock folder row: type = record + 0x34'), (0x532b98, 0x2442fffe, '... - 2'), (0x532b9c, 0x2c420003, '... < 3 (types 2, 3, 4: a folder)'),
    (0x532ba8, 0x0411ff8b, 'the stock folder row: bal is_folderplaying'), (0x532bac, 0x8e04000c, '... with a0 = the record url (+0xc)'),
    (0x532c0c, 0x8e030034, 'the stock folder row: a type 8 record asks is_playing(1, ...)'), (0x532c10, 0x14620008, '(bne type, 8)'),
    # a marked folder in the stock Delete and Add (class 1, docs/modules/folders.md): both read the record's type and load the folder with toolsLoadDirectory
    (0x4e1560, 0x8c430034, 'batch_delete_file class 1 loop: type = record + 0x34'), (0x4e1564, 0x24020004, '... compared with 4 (a folder)'), (0x4e1568, 0x14620033, '(bne: any other type is a file row)'),
    (0x4e157c, 0x8f99b804, 'a folder is read with toolsLoadDirectory(url) (GOT), its type 8 files leave the library'),
    (0x4e12c8, 0x1443001f, 'remove_file: a regular file (S_IFREG) is removed'), (0x4e1348, 0x1443ffe5, 'remove_file: a directory (S_IFDIR) ...'), (0x4e1368, 0x24c6b294, '... runs system of the string at 0x74b294, rm -rf of the path'),
    (0x4db00c, 0x1262002a, 'batch_add_file class 1: a type 4 record (a folder) is expanded ...'), (0x4db0cc, 0x8f99b804, '... with toolsLoadDirectory(url)'),
    (0x4db114, 0x8c430034, '... and each type 8 record of it'), (0x4db11c, 0x14620080, '(bne type, 8: skipped) is added'),
)
RADIO_PINS = (   # (address, stock word, what it proves)
    (0x4e08c4, 0x3c1c0052, 'stop_player prologue'), (0x4e08c8, 0x279c360c, 'stop_player prologue'), (0x4e08cc, 0x0399e021, 'stop_player prologue'),
    (0x4e08e0, 0x0320f809, 'stop_player: jalr mclGetPlayStatus (1 = stopped: nothing to stop)'), (0x4e08f8, 0x0320f809, 'stop_player: jalr mclSetMute(1)'),
    (0x4e091c, 0x0320f809, 'stop_player: jalr mclStop'),
    (0x4d6f68, 0x3c1c0053, 'set_outputchannel prologue'), (0x4d6f6c, 0x279ccf68, 'set_outputchannel prologue'), (0x4d6f70, 0x0399e021, 'set_outputchannel prologue'),
    (0x4e4688, 0x00003025, 'start_player: move a2, zero (set_outputchannel(output, mode, 0))'), (0x4e4690, 0x02002825, 'start_player: move a1, s0 (the mode)'),
    (0x4e4694, 0x8f82a984, 'start_player: lw v0, GOT g_headset_output (0xa05a10)'), (0x4e469c, 0x0411ca32, 'start_player: bal set_outputchannel'),
    (0x4e46a0, 0x8c440000, 'start_player: lw a0, (v0): the output is its first argument'),
    (0x4d6cf8, 0x3c1c0053, 'set_devicevolume prologue'), (0x4d6cfc, 0x279cd1d8, 'set_devicevolume prologue'), (0x4d6d00, 0x0399e021, 'set_devicevolume prologue'),
    (0x5d6080, 0x3c1c0043, 'mclSetPcmMode prologue'), (0x5d6084, 0x279cde50, 'mclSetPcmMode prologue'), (0x5d6088, 0x0399e021, 'mclSetPcmMode prologue'),
    (0x5d4dac, 0x3c1c0043, 'mclSetMute prologue'), (0x5d4db0, 0x279cf124, 'mclSetMute prologue'), (0x5d4db4, 0x0399e021, 'mclSetMute prologue'),
    (0x5d45a4, 0x3c1c0043, 'mclGetOutputWay prologue'), (0x5d45a8, 0x279cf92c, 'mclGetOutputWay prologue'), (0x5d45ac, 0x0399e021, 'mclGetOutputWay prologue'),
    (0x5d5c1c, 0x3c1c0043, 'mclSetDacPwr prologue'), (0x5d5c20, 0x279ce2b4, 'mclSetDacPwr prologue'), (0x5d5c24, 0x0399e021, 'mclSetDacPwr prologue'),
    (0x5d5184, 0x3c1c0043, 'mcl_tidalStartPlayer prologue'), (0x5d5188, 0x279ced4c, 'mcl_tidalStartPlayer prologue'), (0x5d518c, 0x0399e021, 'mcl_tidalStartPlayer prologue'),
    (0x5d244c, 0x3c1c0043, 'mclStop prologue'), (0x5d2450, 0x279c1a84, 'mclStop prologue'), (0x5d2454, 0x0399e021, 'mclStop prologue'),
    (0x5d436c, 0x3c1c0043, 'mclGetHciplayerStatus prologue'), (0x5d4370, 0x279cfb64, 'mclGetHciplayerStatus prologue'), (0x5d4374, 0x0399e021, 'mclGetHciplayerStatus prologue'),
    (0x5d4380, 0x9042ab8b, 'mclGetHciplayerStatus: lbu v0, 0xa0ab8b (hciplayer says "playing")'), (0x5d3654, 0x8c42abe4, 'mclGetPlayStatus: lw v0, 0xa0abe4 (1 stopped, 2 playing, 3 paused)'),
    (0x5d2604, 0x3c1c0043, 'mclSetPause prologue'), (0x5d2608, 0x279c18cc, 'mclSetPause prologue'), (0x5d260c, 0x0399e021, 'mclSetPause prologue'),
    (0x5d2668, 0x3c1c0043, 'mclSetResume prologue'), (0x5d266c, 0x279c1868, 'mclSetResume prologue'), (0x5d2670, 0x0399e021, 'mclSetResume prologue'),
    (0x4e2310, 0x27bdffd8, 'save_stop_player: addiu sp, sp, -0x28 (the trampoline resumes here)'), (0x4e23a0, 0x0320f809, 'save_stop_player: jalr mclStop (after mclSetMute(1), usleep)'),
    (0x4e23f4, 0x27bdffd8, 'save_start_player: addiu sp, sp, -0x28 (the trampoline resumes here)'), (0x4e2458, 0x0320f809, 'save_start_player: jalr mclStartPlayer (the saved status is not 1)'),
    (0x5d530c, 0x27bdf9d0, 'mclStartPlayer: addiu sp, sp, -0x630 (the trampoline resumes here)'),
    (0x4cd598, 0x27bdffd0, 'on_backtoplayer_onclick: addiu sp, sp, -0x30 (the trampoline resumes here)'),
    (0x4cf04c, 0x8e020000, 'on_wm_idle_status: lw v0, (dacoff_time) while nothing plays'), (0x4cf054, 0x24420001, 'on_wm_idle_status: addiu v0, v0, 1'),
    (0x4cf058, 0xae020000, 'on_wm_idle_status: sw v0, (dacoff_time)'), (0x4cf05c, 0x2842001f, 'on_wm_idle_status: slti v0, v0, 31'),
    (0x4cf068, 0x0320f809, 'on_wm_idle_status: jalr mclSetDacPwr(0) past 30 (a playing track zeroes the counter @0x4cee3c)'), (0x4cee3c, 0xae000000, 'on_wm_idle_status: sw zero, (dacoff_time) while playing'),
)
PLAYMORE_PINS = (   # (address, stock word, what it proves)
    (0x479cd0, 0x10800059, 'init: beqz a0 (the trampoline resumes here)'),
    # stock's Delete handler 0x4791f4, which patch/playmore.c pm_on_delete does over (and stops): the confirm's kind, its two answers and what each deletes
    (0x479260, 0x24020003, 'Delete: the confirm is kind 3'), (0x47929c, 0x2403000a, 'Delete: the answer 0xa'), (0x4792a8, 0x24030014, 'Delete: the answer 0x14'),
    (0x4792b0, 0x24040001, 'Delete: delete_playqueue_file(1) for 0x14 (the delay slot of its branch)'), (0x4792d8, 0x0320f809, 'Delete: jalr delete_playqueue_file'),
    (0x4e48d8, 0x3c1c0052, 'delete_playqueue_file prologue'), (0x4e49b0, 0x0320f809, 'delete_playqueue_file: jalr toolsClearDeqItem (the playing row leaves the queue)'),
    (0x479d10, 0x24060082, 'init: widget_move(dialog, 0, 130): the sheet is pinned at y 130'),
    (0x4d1238, 0x24a59f78, 'dispatcher: "dialog/playmore_dialog" string'),
    (0x4d1244, 0x8f99b5d4, 'dispatcher: loads dialog_playmore_dialog_init from the GOT'),
    (0x4d124c, 0x0320f809, 'dispatcher: jalr t9'),
    (0x478ac8, 0x8c830004, 'tap handler: dialog->y'), (0x478acc, 0x8ca2001c, 'tap handler: pointer_event y (a tap above the sheet closes it)'),
    (0x479ce0, 0x2405012c, 'init: widget_on(dialog, EVT_WINDOW_TO_BG 0x12c, 0x4789f0): the stock to-background handler, on the dialog'),
    (0x478a1c, 0x24060082, 'to-background handler 0x4789f0: widget_move(dialog, 0, 130), which our handler undoes'),
    # why ours is bound on the list_view and not on the dialog: a handler bound later on the dialog would run before the stock one
    (0x6f466c, 0xac430020, 'emitter_on_with_tag: new->next = emitter->items'),
    (0x6f4670, 0xae020000, 'emitter_on_with_tag: emitter->items = new (a handler goes to the head: the newest runs first)'),
    (0x6f45a0, 0x00009825, 'emitter_dispatch: RET_OK after the last handler (the dialog\'s window event goes on to its children)'),
    (0x678870, 0x0411c0c3, 'window_manager_dispatch_window_event: bal widget_dispatch_recursive (the window event reaches the children)'),
    (0x668ae4, 0x0320f809, 'widget_foreach: visit(widget) first'),
    (0x668af0, 0x1440000b, 'widget_foreach: then its children, if the visit returned RET_OK (the dialog before its list_view)'),
    (0x60c53c, 0x1443fff6, 'list_view_on_event: RET_OK for an event it does not handle (0x12c reaches the list_view\'s emitter)'),
    # why a restacked Power page needs no refresh of ours (pm_on_sleep): stock's restack delivers EVT_WINDOW_TO_FG to it, and the handler its init bound for that event runs the page's refresh
    (0x6789e8, 0x2405012d, 'window_manager_switch_to (animation 0): a1 = EVT_WINDOW_TO_FG 0x12d ...'), (0x6789f4, 0x0411ff88, '... window_manager_dispatch_window_event(new window, 0x12d)'),
    (0x4a9d34, 0x2405012d, 'powermanager_page init: widget_on(win, 0x12d, ...)'), (0x4a9d44, 0x24c69b2c, 'its handler is 0x4a9b2c'), (0x4a9d50, 0x0320f809, 'jalr widget_on'),
    (0x4a9b48, 0x27399924, 'handler 0x4a9b2c: t9 = 0x4a9924, the page refresh'), (0x4a9b50, 0x0411ff74, 'bal 0x4a9924, with a0 = the window (the delay slot move s0, a0)'),
)
PULLDOWN_OPEN_SITES = (0x4cd894, 0x4cd8bc)
PULLDOWN_PINS = (   # (address, stock word, what it proves)
    (0x475f10, 0x1080003c, 'init: beqz a0 (the trampoline resumes here)'),
    (0x4d1c70, 0x24a59a4c, 'dispatcher: "dialog/dropdown_dialog" string'),
    (0x4d1c7c, 0x8f99b69c, 'dispatcher: loads dialog_dropdown_dialog_init from the GOT'),
    (0x4d1c84, 0x0320f809, 'dispatcher: jalr t9'),
    (0x475f34, 0x24050103, 'init: widget_on(dialog, 0x103 pointer up, 0x4752f0)'),
    (0x475f54, 0x240500ff, 'init: widget_on(dialog, 0xff pointer down, 0x47514c)'),
    (0x475f74, 0x24050101, 'init: widget_on(dialog, 0x101 pointer move, 0x4755e8)'),
    (0x475f94, 0x2405012e, 'init: widget_on(dialog, 0x12e, 0x4750ec)'),
    (0x473fc8, 0x2405010c, 'tile visitor 0x473f30: widget_on(tile image, EVT_CLICK 0x10c): the tiles take pointer clicks only, no key event'),
    (0x475fd8, 0x0411fdb5, 'init: bal dropdown_showface (0x4756b0), the last call before the init returns 0'),
)
PULLDOWN_FLAG_PINS = (   # (address, stock word, what it proves)
    (0x4cd874, 0x8fbc0010, 'on_wm_tsmove_fun: lw gp, 0x10(sp) after navigator_to("dialog/dropdown_dialog") returned 0xd'),
    (0x4cd878, 0x8f82a95c, 'on_wm_tsmove_fun: lw v0, GOT playsetinto_flag (0xa05a4c): the flag of 2 opens Playback Settings'),
    (0x4cd888, 0x8f82a96c, 'on_wm_tsmove_fun: lw v0, GOT syssetinto_flag (0xa05a48)'),
    (0x4cd88c, 0x8f848020, 'on_wm_tsmove_fun: lw a0, GOT page 0x750000'), (0x4cd890, 0x8f99a704, 'on_wm_tsmove_fun: lw t9, GOT navigator_to'),
    (PULLDOWN_OPEN_SITES[0] + 4, 0x24849a64, 'its delay slot: a0 = "playset/playset_page"'),
    (0x4cd8a0, 0x8f82a96c, 'on_wm_tsmove_fun: lw v0, GOT syssetinto_flag (the second test)'),
    (PULLDOWN_OPEN_SITES[1] + 4, 0x24849a7c, 'its delay slot: a0 = "systemset/sysset_page"'),
    (0x4754e8, 0x8f91a96c, 'System tile handler 0x4754c8: lw s1, GOT syssetinto_flag'), (0x4754f4, 0x14400013, 'System tile handler: bnez v0, return (a nonzero flag does nothing)'),
    (0x475578, 0x8f91a95c, 'Playback tile handler 0x475558: lw s1, GOT playsetinto_flag'), (0x475584, 0x14400013, 'Playback tile handler: bnez v0, return'),
)
