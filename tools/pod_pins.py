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
# Now Playing screen-off pause (patch/nowplaying.c np_dark_set): pauses stock's 500 ms timer and title/artist marquees while dark, refreshes synchronously on wake.
NP_IDLE_PINS = (   # (address, stock word, what it proves)
    (0x53c210, 0x3c1c004c, 'player_timer_start: PIC prologue'),
    (0x53c25c, 0x240601f4, 'player_timer_start: a2 = 500 ms (0x1f4)'),
    (0x53c268, 0x0320f809, 'player_timer_start: jalr widget_add_timer'),
    (0x53c758, 0x3c1c004c, 'player_timer_clear: PIC prologue'),
    (0x53bab4, 0x3c1c004d, 'show_player_face: PIC prologue'),
    (0x609648, 0x3c1c0040, 'hscroll_label_start: PIC prologue'),
    (0x6097e8, 0x3c1c0040, 'hscroll_label_stop: PIC prologue'),
)
# Boot cache-dropper thread (patch/power.c m1plus_check_cpumem, payload hook 41): stock's platform_init spawns detached thread check_cpumem (0x50b810)
# which opens /proc/sys/vm/drop_caches once and writes "3" every ~6 s without checking free memory. On the kill switch the hook falls back to stock.
CHECK_CPUMEM_PINS = (   # (address, stock word, what it proves)
    (0x50b81c, 0x27bdffd8, 'check_cpumem: addiu sp, sp, -0x28 (the trampoline resumes here)'),
    (0x50b830, 0x2484f040, 'check_cpumem: a0 = "/proc/sys/vm/drop_caches" (0x74f040)'),
    (0x50b844, 0x0320f809, 'check_cpumem: jalr open64'),
    (0x50b878, 0x0320f809, 'check_cpumem: jalr write(fd, "3", 1)'),
    (0x50bca8, 0x8f86be14, 'platform_init: lw a2, GOT check_cpumem (0x50b810)'),
    (0x50bcb0, 0x0320f809, 'platform_init: jalr pthread_create(..., check_cpumem, NULL)'),
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
    # Lock screen 20 ms timer (0x53fc68) and refresh (0x53f520, 0x53f9b4) replaced in m1plus_lockscreen_init (patch/lockscreen.c lks_take):
    # stock adds 0x53fc68 with period 20 ms (0x14) and stores its id in "timer_idex"; while LOCK_DELAY (0x97ccf0) > 0 it runs the wake backlight
    # countdown, then calls 0x53f520(win, a1) where a1 = 0 updates img_battery / pgbar_battery only and returns at 0x53f64c (bnez s4, 0x53f698; b 0x53f6bc).
    (0x53fe28, 0x24060014, 'screensaver_page_init: a2 = 20 ms for widget_add_timer'),
    (0x53fe34, 0x0320f809, 'screensaver_page_init: jalr widget_add_timer'),
    (0x53fe38, 0x24a5fc68, 'screensaver_page_init: a1 = 0x53fc68 (the 20 ms timer callback)'),
    (0x53fc68, 0x3c1c004c, 'screensaver timer 0x53fc68: PIC prologue'),
    (0x53fc88, 0x8c62ccf0, 'screensaver timer: lw v0, -0x3310(0x980000) = LOCK_DELAY (0x97ccf0)'),
    (0x53fcec, 0x90430000, 'screensaver timer: lbu v1, LOCK_TRACK_DIRTY (0xa05a60)'),
    (0x53fd1c, 0x8f82b8a8, 'screensaver timer: lw v0, GOT LOCK_COVER_DIRTY (0xa05a5c)'),
    (0x53f520, 0x3c1c004c, 'screensaver refresh 0x53f520: PIC prologue'),
    (0x53f64c, 0x16800012, 'screensaver refresh: bnez s4 (a1), 0x53f698 (a1 == 0 skips track/button work)'),
    (0x53f654, 0x10000019, 'screensaver refresh: b 0x53f6bc (a1 == 0 returns after battery update)'),
    (0x53f9b4, 0x3c1c004c, 'screensaver cover reload 0x53f9b4: PIC prologue'),
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
    # Screen Rotation (patch/display.c disp_rotate_toggle): stock's systemset/screenrotate_page (0x4ab0a4). listitem0 is bound to 0x4ab03c (0 degrees), listitem1 to 0x4aafd0 (180 degrees). Each returns when rotate_mode is
    # the choice already (0x4ab05c, 0x4aaff8), else calls the shared 0x4aae68(win, choice) (unmarks the old row; stores the word in the delay slot of write_int_config(choice, "SYSSET", "ROTATEMODE") unless it is the
    # word already), then tk_set_lcd_orientation(0 / 0xb4) and stores 1 in the byte scr_rotateflag (0xa05a58). config_init keeps 0 or 1 and awtk_configinit (0x4ccb5c, at 0x4ccbd4) applies the word at boot.
    (0x4aadd8, 0x24c6b03c, 'rotate page visitor: listitem0 -> handler 0x4ab03c (0 degrees)'), (0x4aae0c, 0x24c6afd0, 'rotate page visitor: listitem1 -> handler 0x4aafd0 (180 degrees)'),
    (0x4ab04c, 0x8f82ab4c, 'rotate 0 handler 0x4ab03c: lw v0, GOT rotate_mode (0xa05a9c)'), (0x4ab05c, 0x1040000e, 'rotate 0 handler: beqz v0: already 0 does nothing'),
    (0x4ab06c, 0x0411ff7e, 'rotate 0 handler: bal 0x4aae68'), (0x4ab070, 0x00002825, 'rotate 0 handler: a1 = 0'), (0x4ab07c, 0x0320f809, 'rotate 0 handler: jalr tk_set_lcd_orientation'),
    (0x4ab080, 0x00002025, 'rotate 0 handler: a0 = 0'), (0x4ab08c, 0x8f82a828, 'rotate 0 handler: lw v0, GOT scr_rotateflag (0xa05a58)'), (0x4ab084, 0x24030001, 'rotate 0 handler: v1 = 1'),
    (0x4ab090, 0xa0430000, 'rotate 0 handler: sb v1 (1), (v0): the flag after the orientation call'),
    (0x4aafe0, 0x8f82ab4c, 'rotate 180 handler 0x4aafd0: lw v0, GOT rotate_mode'), (0x4aafec, 0x24100001, 'rotate 180 handler: s0 = 1'), (0x4aaff8, 0x1050000b, 'rotate 180 handler: beq v0, s0: already 1 does nothing'),
    (0x4ab004, 0x0411ff98, 'rotate 180 handler: bal 0x4aae68'), (0x4ab008, 0x24050001, 'rotate 180 handler: a1 = 1'), (0x4ab014, 0x0320f809, 'rotate 180 handler: jalr tk_set_lcd_orientation'),
    (0x4ab018, 0x240400b4, 'rotate 180 handler: a0 = 0xb4 (180)'), (0x4ab020, 0x8f82a828, 'rotate 180 handler: lw v0, GOT scr_rotateflag'), (0x4ab024, 0xa0500000, 'rotate 180 handler: sb s0 (1), (v0): the flag after the orientation call'),
    (0x4aaf10, 0x8f82ab4c, 'rotate shared 0x4aae68: lw v0, GOT rotate_mode'), (0x4aaf14, 0x8c520000, 'rotate shared: lw s2, (v0): the old word'), (0x4aaf18, 0x12500023, 'rotate shared: beq s2, s0: the same word saves nothing'),
    (0x4aaf8c, 0x02002025, 'rotate shared: a0 = the choice'), (0x4aaf98, 0x24c68608, 'rotate shared: a2 = "ROTATEMODE"'), (0x4aaf9c, 0xae700000, 'rotate shared: sw s0, (s3) in the save\'s delay slot: the word first'),
    (0x4aafa0, 0x0320f809, 'rotate shared: jalr write_int_config'), (0x4aafa4, 0x24a54540, 'rotate shared: a1 = "SYSSET"'),
    (0x5f35e8, 0x3c1c0041, 'tk_set_lcd_orientation: prologue (1/2)'), (0x5f35ec, 0x279c08e8, 'tk_set_lcd_orientation: prologue (2/2)'),
    (0x4e64a0, 0x2c430002, 'config_init: ROTATEMODE sltiu v1, v0, 2'), (0x4e64a4, 0x0003100a, 'config_init: ROTATEMODE movz v0, zero, v1: 2 and up become 0'), (0x4e64bc, 0xac620000, 'config_init: ROTATEMODE stored as a word'),
    (0x4ccbdc, 0x10400002, 'awtk_configinit 0x4ccb5c: beqz rotate_mode: 0 keeps orientation 0'), (0x4ccbe4, 0x240400b4, 'awtk_configinit: a0 = 180 for a non-zero word, then tk_set_lcd_orientation'),
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
# Settings > Buttons & Power (patch/keyspower.c, docs/modules/keyspower.md): the four controls of stock's systemset/keylock_page, the sysset list's row 7 and systemset/powermanager_page, as their click handlers
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
    # Car Mode (patch/keyspower.c kp_car_toggle): row 6 of the sysset list. The click handler 0x4ad7b0 maps the row's name (atoi) through the table 0x97c8c0 and jumps through 0x748ae0; entry 6 is the case 0x4ad84c: the byte car_mode
    # (0xa05aa6) xor 1 stored in the delay slot of write_int_config(byte, "SYSSET", "CARMODE") (the byte first), then the row's switch image (img_carmode%d: sset_on or sset_off), then 0 into the word carmode_startflag
    # (0xa059dc) on both image paths (0x4ad918 joins 0x4ad8e8). config_init keeps 0 or 1 (a byte). What the byte does is read off its readers: to_poweroptions (the standby and shutdown countdowns run only for 0), check_usb_status
    # and check_otg_status (return at once for non-zero), home_page_init and save_memoryplay_info / memeory_startplayer (the last track is saved and resumed at start for non-zero, as Memory Playback does).
    (0x748af8, 0xffaa997c, 'sysset click jump table 0x748ae0: entry 6 is 0x4ad84c (Car Mode)'), (0x97c8d8, 0x00000006, 'sysset row table 0x97c8c0: row 6 maps to case 6'),
    (0x4ad84c, 0x8f92b064, 'car mode case 0x4ad84c: lw s2, GOT car_mode (0xa05aa6)'), (0x4ad860, 0x92440000, 'car mode: lbu a0, (s2)'), (0x4ad864, 0x24c68980, 'car mode: a2 = "CARMODE"'), (0x4ad868, 0x24a54540, 'car mode: a1 = "SYSSET"'),
    (0x4ad870, 0x38840001, 'car mode: xori a0, a0, 1'), (0x4ad874, 0x0320f809, 'car mode: jalr write_int_config'), (0x4ad878, 0xa2440000, 'car mode: sb a0, (s2) in the delay slot: the byte first'),
    (0x4ad8d8, 0x1040000f, 'car mode: beqz: the image is sset_off for 0 (0x4ad918 joins 0x4ad8e8), else sset_on'), (0x4ad91c, 0x1000fff2, 'car mode: sset_off path branches back to 0x4ad8e8'),
    (0x4ad8e8, 0x0320f809, 'car mode: jalr image_base_set_image (both paths)'), (0x4ad8f4, 0x8f82b068, 'car mode: lw v0, GOT carmode_startflag (0xa059dc)'), (0x4ad8f8, 0xac400000, 'car mode: sw zero, (v0): cleared after the image'),
    (0x4e5f14, 0x2c430002, 'config_init: CARMODE sltiu v1, v0, 2'), (0x4e5f2c, 0x30420001, 'config_init: CARMODE andi v0, v0, 1'), (0x4e5f34, 0xa0620000, 'config_init: CARMODE stored as a byte'),
    (0x4ce624, 0x8f82b064, 'to_poweroptions: lw v0, GOT car_mode (standby countdown)'), (0x4ce62c, 0x1440002b, 'to_poweroptions: bnez car_mode skips the standby countdown'),
    (0x4ce6ec, 0x8f82b064, 'to_poweroptions: lw v0, GOT car_mode (shutdown countdown)'), (0x4ce6f4, 0x14400024, 'to_poweroptions: bnez car_mode skips the shutdown countdown'),
    (0x4ce214, 0x90420000, 'check_usb_status: lbu v0, (car_mode)'), (0x4ce218, 0x10400003, 'check_usb_status: beqz: only non-zero car mode returns 0 at once'),
    (0x4cdf70, 0x90420000, 'check_otg_status: lbu v0, (car_mode)'), (0x4cdf74, 0x1440002b, 'check_otg_status: bnez: non-zero car mode returns 0 at once'),
    (0x534e6c, 0x8f82b064, 'home_page_init: lw v0, GOT car_mode (after the Memory Playback word 0xa05ac4)'), (0x534e74, 0x10400036, 'home_page_init: beqz car_mode: without Memory Playback and Car Mode nothing is resumed'),
    (0x4e33c4, 0x8f82b064, 'save_memoryplay_info: lw v0, GOT car_mode (after the Memory Playback word)'), (0x4e33cc, 0x1040fff4, 'save_memoryplay_info: beqz car_mode: the position is saved for Car Mode too'),
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
    (0x5d26dc, 0x3c1c0043, 'mclSetSeek prologue'), (0x5d26e0, 0x279c17f4, 'mclSetSeek prologue'), (0x5d26e4, 0x0399e021, 'mclSetSeek prologue'),
    (0x5d2704, 0x9042ab8a, 'mclSetSeek: lbu v0, -0x5476(v0): the hciplayer connected flag (0: returns -1)'),
    (0x5d2724, 0x24a564e8, 'mclSetSeek: addiu a1, a1, 0x64e8: the "{mcl-seek\\%d}" format @0x7564e8'),
    (0x5d2768, 0x0320f809, 'mclSetSeek: jalr send'),
)
WIFIHUB_SITE = 0x4b1460   # the Wi-Fi row of the All System Settings hub: its jalr navigator_to("systemset/wifi_page") becomes jal wifi_hub_open (patch/wifipage.c, docs/modules/payload.md hook 21)
BTHUB_SITE = 0x4b1428   # the Bluetooth row of the All System Settings hub: its jalr navigator_to("systemset/bluetooth_page") becomes jal bt_hub_open (patch/btpage.c, docs/modules/payload.md hook 32)
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
    # the Bluetooth hub row's thunk @0x4b1408 (payload hook 32): its jalr navigator_to @0x4b1428 becomes jal bt_hub_open; the thunk's prologue, GOT loads, delay slot and return value are stock's
    (0x4b1408, 0x3c1c0055, 'the Bluetooth hub row thunk prologue'), (0x4b140c, 0x279c2ac8, 'the Bluetooth hub row thunk prologue'), (0x4b1410, 0x0399e021, 'the Bluetooth hub row thunk prologue'),
    (0x4b1418, 0x8f848020, 'the Bluetooth hub row: lw a0, GOT page 0x750000'), (0x4b141c, 0x8f99a704, 'the Bluetooth hub row: lw t9, GOT navigator_to'),
    (BTHUB_SITE, 0x0320f809, 'the Bluetooth hub row (0x4b1408): jalr navigator_to'), (0x4b142c, 0x24848f00, 'its delay slot: a0 = "systemset/bluetooth_page"'), (0x4b1430, 0x00001025, 'the Bluetooth hub row: move v0, zero (the result is not used)'),
    (0x4ad830, 0x0320f809, 'the Settings rows\' shared call: jalr navigator_to'), (0x4ada74, 0x24848ab4, 'Settings row 3: a0 = "systemset/display_page" (our Display page takes its place)'),
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
ID3_SITE = 0x4dff4c   # get_id3info's jalr strcpy of the parsed path, replaced by jal pc_id3_path (docs/modules/podcasts.md); q2-pod's ID3_PATH is the same site in its demo
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
COVER_PINS = (   # (address, stock word, what it proves): stock's cover extraction as patch/covercache.c art_embedded / art_folder and patch/pccover.c pv_cover reproduce it (docs/modules/covercache.md "Cover resampling")
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
    # the Find Cover & Lyrics page reloads the playing track's lyrics after a save (patch/onlineart.c oa_on_save, docs/modules/onlineart.md), as stock does after its own lyric download (a click handler on the UI thread, registered by widget_on(0x10c) @0x536d8c)
    (0x5d41e4, 0x3c1c0043, 'mclLoadExLyric prologue (1/3): no arguments; it clears the lyric deque under its mutex, then reads the play position\'s .lrc'), (0x5d41e8, 0x279cfcec, 'mclLoadExLyric prologue (2/3)'), (0x5d41ec, 0x0399e021, 'mclLoadExLyric prologue (3/3)'),
    (0x5d4240, 0x0440000e, 'mclLoadExLyric: bltz the play position: nothing is read for no position (then it tail-calls the loader 0x5d3670)'),
    (0x5d3670, 0x3c1c0043, 'the .lrc loader 0x5d3670 prologue (1/3): fopen / fread of the file and the deque pushed under the lyric mutex'), (0x5d3674, 0x279c0860, 'the loader prologue (2/3)'), (0x5d3678, 0x0399e021, 'the loader prologue (3/3)'),
    (0x536d8c, 0x0320f809, 'the click handler\'s registration: jalr widget_on(widget, 0x10c, 0x5377ec): the handler that ...'),
    (0x537cbc, 0x8f99c220, '... calls mclLoadExLyric after it copies a downloaded lyric file: lw t9, GOT mclLoadExLyric'), (0x537cc0, 0x0320f809, '... jalr mclLoadExLyric()'),
    (0x537cd0, 0x8f82aa50, '... then lw v0, GOT force_refreshflag (0xa05a63)'), (0x537cd8, 0xa0430000, '... sb 1, force_refreshflag (in the delay slot): the rebuild show_player_face does'),
)
# The stock local .lrc reader 0x5d3670 (only caller mclLoadExLyric 0x5d41e4, a tail call; UI thread) opens the file with fopen(path, "r"); the hook (patch/lyrics.c ly_lrc_open, docs/modules/lyrics.md) hands it a FILE* of
# a cleaned copy of a plain-text lyric file and falls back to stock's fopen, so the parser pinned here must keep reading that copy as it reads a .lrc.
LRCOPEN_SITE = 0x5d3bdc
LRCOPEN_PINS = (   # (address, stock word, what it proves)
    (0x5d3bd4, 0x8f99f25c, 'the .lrc reader: lw t9, GOT fopen'), (0x5d3bd8, 0x266573e8, 'the .lrc reader: a1 = "r" (0x7773e8)'),
    (LRCOPEN_SITE, 0x0320f809, 'the .lrc reader: jalr fopen(path, "r") (the hook replaces it with jal ly_lrc_open)'), (LRCOPEN_SITE + 4, 0x02002025, 'its delay slot: a0 = the path (s0)'),
    (0x5d3be4, 0x8fbc0038, 'the reader: lw gp after the call'), (0x5d3be8, 0x104000a2, 'the reader: a null FILE* is "open lyric file failed!" (stock\'s answer when the hook falls back and the open fails)'), (0x5d3bec, 0x00409025, 'the reader: s2 = the FILE*'),
    (0x5d3ea4, 0x24050600, 'the reader: fgets size 0x600: the hook\'s lines are cut to what fits'), (0x5d3eb4, 0x0320f809, 'the reader: jalr fgets(line, 0x600, file): one line at a time'),
    (0x5d3ec4, 0x041138aa, 'the reader: bal toolsTrimRight(line): trailing blanks and the newline go'), (0x5d3ed0, 0x1040ff4c, 'the reader: an empty line is skipped'),
    (0x5d3edc, 0x2405005b, 'the reader: a1 = \'[\''), (0x5d3ee0, 0x0320f809, 'the reader: jalr strchr(line, \'[\')'), (0x5d3eec, 0x1040ff45, 'the reader: a line without \'[\' is skipped (so the hook gives every line a tag)'),
    (0x5d3ef8, 0x2405005d, 'the reader: a1 = \']\''), (0x5d3efc, 0x0320f809, 'the reader: jalr strrchr(from the first \'[\', \']\'): the text is what follows the LAST \']\''),
    (0x5d3fbc, 0x2442ffd0, 'the reader: the tag\'s first char minus \'0\''), (0x5d3fc4, 0x2c42000a, 'the reader: ... below 10'), (0x5d3fc8, 0x1040ff0e, 'the reader: a tag that does not start with a digit is skipped (so the hook writes numeric tags)'),
    (0x5d3fd8, 0x04113c11, 'the reader: bal toolsTimeConvert(tag): the time of the line'),
    (0x5d4158, 0x83a20e40, 'the reader: lb the text'), (0x5d415c, 0x1040000d, 'the reader: an empty text takes the path at 0x5d4194'), (0x5d4160, 0x8f99f2b4, 'the reader: lw t9, GOT malloc (delay slot)'),
    (0x5d4194, 0x0320f809, 'the reader: jalr malloc(2) ...'), (0x5d4198, 0x24040002, '... a0 = 2'), (0x5d419c, 0x02802825, '... a1 = s4, the string at 0x757700 (" "; s4 set at 0x5d3bf0 / 0x5d3bfc): an empty text becomes " "'),
    (0x5d3bf0, 0x8f948020, 'the reader: lw s4, GOT page 0x750000'), (0x5d3bfc, 0x26947700, 'the reader: s4 += 0x7700 (" ")'),
    (0x5d4270, 0x27393670, 'mclLoadExLyric: addiu t9 = 0x5d3670 (the reader) ...'), (0x5d4274, 0x1000fcfe, '... b 0x5d3670: the tail call; the reader is entered only here'),
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
    # External power (patch/power.c, docs/modules/charging.md "External power"): usb_detect (0x4d6f30) reads PD17 through toolsGpioGetValue and returns 1 for level 0; the payload repeats that read
    (0x4d6f30, 0x3c1c0053, 'usb_detect prologue'), (0x4d6f34, 0x279ccfa0, 'usb_detect prologue'), (0x4d6f38, 0x0399e021, 'usb_detect prologue'),
    (0x4d6f40, 0x8f848020, 'usb_detect: lw a0, GOT page 0x750000'), (0x4d6f44, 0x8f99b368, 'usb_detect: lw t9, GOT toolsGpioGetValue'),
    (0x4d6f54, 0x2484a8ec, 'usb_detect: addiu a0, a0, -0x5714 (delay slot): a0 = "PD17" at 0x74a8ec'), (0x4d6f5c, 0x2c420001, 'usb_detect: sltiu v0, v0, 1: level 0 is external power'),
    (0x66d194, 0x8e020008, 'widget_resize: lw v0, 8(s0): widget_t.w'), (0x66d1a0, 0x8e03000c, 'widget_resize: lw v1, 0xc(s0): widget_t.h'),
    (0x66c428, 0x8e040044, 'widget_set_visible: lw a0, 0x44(s0): widget_t.parent, handed to widget_set_need_relayout_children'),
)
# Wake repaint (patch/battery.c bp_light_on / bp_light_off, docs/modules/battery.md "The wake repaint"): screen_action (0x4e71a4, every backlight on / off: awake_screen, the power key's handlers) calls toolSetBackLight (0x5e4f10)
# at 0x4e71cc (on, a0 = brightness + 1 in the delay slot) and 0x4e71fc (off, a0 = 0, nop delay slot). Both `jalr t9` become `jal`; t9 is loaded in the beqz delay slot at 0x4e71c0.
LIGHT_ON_SITE = 0x4e71cc
LIGHT_OFF_SITE = 0x4e71fc
BACKLIGHT_PINS = (
    (0x4e71a4, 0x3c1c0052, 'screen_action prologue'), (0x4e71a8, 0x279ccd2c, 'screen_action prologue'), (0x4e71ac, 0x0399e021, 'screen_action prologue'),
    (0x4e71bc, 0x1080000f, 'screen_action: beqz a0 (off)'), (0x4e71c0, 0x8f99a890, 'screen_action: lw t9, GOT toolSetBackLight (delay slot)'),
    (0x4e71c8, 0x8c440000, 'screen_action: lw a0, (brightness)'), (LIGHT_ON_SITE, 0x0320f809, 'screen_action: jalr toolSetBackLight (on)'), (0x4e71d0, 0x24840001, 'screen_action: addiu a0, a0, 1 (delay slot)'),
    (0x4e71d8, 0x8fbc0010, 'screen_action: lw gp (reloaded after the on call)'),
    (LIGHT_OFF_SITE, 0x0320f809, 'screen_action: jalr toolSetBackLight (off)'), (0x4e7200, 0x00000000, 'screen_action: nop (the delay slot)'), (0x4e7204, 0x8fbc0010, 'screen_action: lw gp (reloaded after the off call)'),
    (0x4e7208, 0x8f99a894, 'screen_action: lw t9, GOT disable_fb'),
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
# SyncLink's room (patch/lineout.c lo_link_show, docs/modules/payload.md hook 40, docs/modules/lineout.md "Room"): both face ticks show img_synclink with `jalr widget_set_visible(img_synclink, 1)` after
# they set the Bluetooth image and after hook 20; the jalr becomes `jal lo_link_show` (a1 = 1 and the delay slot `move a0, s5` stay stock's), which hides SyncLink when stock's marks would run into the clock.
SYNCLINK_SITES = (0x545068, 0x475bb0)   # show_sysbar_face, dropdown_showface
SYNCLINK_PINS = tuple(p for s, f in zip(SYNCLINK_SITES, ('show_sysbar_face', 'dropdown_showface')) for p in (
    (s - 8, 0x8f99a8b8, f'{f}: lw t9, GOT widget_set_visible'), (s - 4, 0x24050001, f'{f}: a1 = 1 (SyncLink connected)'),
    (s, 0x0320f809, f'{f}: jalr widget_set_visible (the hook replaces it)'), (s + 4, 0x02a02025, f'{f}: move a0, s5 (img_synclink; the delay slot)'))) + (
    (0x66c394, 0x3c1c0039, 'widget_set_visible prologue'), (0x66c398, 0x279c7b3c, 'widget_set_visible prologue'),
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
    (0x5d59a8, 0x8c50aae0, 'mclNextSong: the Folder Skip branch calls deque_at(queue, $a1) with the position the end test read (kept by the stub in $s0, which is loaded here before any read)'), (0x5d59ac, 0x12000009, 'mclNextSong: the Folder Skip branch calls deque_at(queue, $a1) with the position the end test read (kept by the stub in $s0, which is loaded here before any read)'), (0x5d59b0, 0x8f99f574, 'mclNextSong: the Folder Skip branch calls deque_at(queue, $a1) with the position the end test read (kept by the stub in $s0, which is loaded here before any read)'), (0x5d59b4, 0x0320f809, 'mclNextSong: the Folder Skip branch calls deque_at(queue, $a1) with the position the end test read (kept by the stub in $s0, which is loaded here before any read)'), (0x5d59b8, 0x8e440000, 'mclNextSong: the Folder Skip branch calls deque_at(queue, $a1) with the position the end test read (kept by the stub in $s0, which is loaded here before any read)'),
    (0x5d59ec, 0x8c50abec, 'mclNextSong: the automatic stop loads $s0 (the socket) before it reads it'),
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
# Settings > General's direct rows (docs/modules/settings.md "General"): the stock pages ACT_STOCK opens (a plain navigator_to of the name, no context; the payload's own table holds the names, these pins
# prove each name is the one stock's own list or hub uses). The usbset page has no opener in V2.1 other than the page registry (0x4d0c10: the init dispatcher by name).
STOCKROWS_PINS = (   # (address, stock word, what it proves)
    (0x4b13f0, 0x0320f809, 'the SyncLink hub row (0x4b13d0): jalr navigator_to'), (0x4b13f4, 0x24848ee8, 'its delay slot: a0 = "systemset/synclink_page"'),
    (0x4d0c10, 0x24a59f14, 'page registry: a1 = "systemset/usbset_page" (strcmp, then systemset_usbset_page_init)'),
)
PLAYLIST_EXPORT = 0x53dd34
PLAYLIST_PINS = (   # (address, stock word, what it proves)
    (PLAYLIST_EXPORT, 0x3c1c004c, 'export click handler prologue'), (PLAYLIST_EXPORT + 4, 0x279c619c, 'export click handler prologue'),
    (PLAYLIST_EXPORT + 8, 0x0399e021, 'export click handler prologue'),
    (0x4ef394, 0x3c1c0051, 'importPlayList prologue'), (0x4ef398, 0x279c4b3c, 'importPlayList prologue'), (0x4ef39c, 0x0399e021, 'importPlayList prologue'),
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
    # Reorder (patch/songops.c so_reorder_rows): a failed statement closes the shared handle (rolling back what is open on it) and clears it; stock's scan insert sends BEGIN only while
    # the transaction word DB_TX is 0, so a word above 0 is a transaction of stock's open on the handle
    (0x5ef028, 0x0320f809, 'toolsUpdateDbTable error path: jalr sqlite3_close(the shared handle)'), (0x5ef034, 0xae00ac74, 'toolsUpdateDbTable error path: sw zero, the handle 0xa0ac74'),
    (0x5edf30, 0x8e22b080, 'scan insert: lw v0, the transaction word 0xa0b080'), (0x5edf34, 0x1440000c, 'scan insert: bnez v0: BEGIN only while the word is 0'),
    (0x5ef370, 0x3c1c0041, 'toolsDeleteItemById prologue'), (0x5ef374, 0x279c4b60, 'toolsDeleteItemById prologue'), (0x5ef378, 0x0399e021, 'toolsDeleteItemById prologue'),
    (0x5ef3f8, 0x24c67ec0, 'toolsDeleteItemById: a2 = "delete from %s where id=%d" 0x757ec0'), (0x5ef418, 0x0320f809, 'toolsDeleteItemById: jalr sqlite3_exec'),
    (0x4edfc4, 0x0320f809, 'deletePlaylist: jalr toolsDeleteItemById("playlist", the database path, id): stock\'s own use on this table'),
    (0x4e22b0, 0x04112f39, 'batch_delete_file, class 0xf00b loop: bal deletePlaylist 0x4edf98'), (0x4e22d4, 0x04112f41, 'batch_delete_file, class 0xf00b loop: bal deleteAllMusicByPlaylist 0x4edfdc'),
    # Remove from Playlist (patch/songs.c sg_remove_one): a playlist song record's REC_DISC is its cd_num, the playlist's id, because getMusicByPlayList reads its rows with the library's song row callback
    (0x4ede28, 0x24c69058, 'getMusicByPlayList: a2 = the song row callback 0x4e9058 (REC_DISC = cd_num)'),
    # Rename Playlist (patch/songops.c so_rename_pl): createPlayListItem copies the name into the record's +8 and +0x10, and toolsInsertDbTable writes +8 as the second value (column filename) and +0x10
    # as the seventh (column name) of `create table %s(id, filename, fileurl, album, songer, style, name, ...)`: a playlist's name is in both columns
    (0x4eee04, 0xafa20020, 'createPlayListItem: rec+8 = a copy of the name'), (0x4eee3c, 0xafa20028, 'createPlayListItem: rec+0x10 = a copy of the name'),
    (0x5ee388, 0x8e070008, 'toolsInsertDbTable: a3 = rec+8 (the filename value)'), (0x5ee50c, 0x8e070010, 'toolsInsertDbTable: a3 = rec+0x10 (the name value)'),
    (0x5ee644, 0xafbe0014, 'toolsInsertDbTable: the second value (filename) is the rec+8 copy'), (0x5ee654, 0xafb50028, 'toolsInsertDbTable: the seventh value (name) is the rec+0x10 copy'),
    (0x5ee67c, 0x24c67d20, 'toolsInsertDbTable: a2 = "insert into %s values(%d,\'%s\',..." 0x757d20'),
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
# ---- List gestures (patch/scroll.c, docs/modules/gestures.md) --------------------------------------------
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
    # stock's Add to playlist handler 0x4798f0, which patch/playmore.c pm_on_addpl does over (and stops) with our picker: the call, its refusal and the stock picker's context
    (0x4efdcc, 0x3c1c0051, 'player_addplayList prologue'), (0x4efdd0, 0x279c4104, 'player_addplayList prologue'), (0x4efdd4, 0x0399e021, 'player_addplayList prologue'),
    (0x4f0020, 0x0411a8e3, 'player_addplayList: bal select_recordinit(the queue\'s size)'), (0x4f0030, 0x0411a900, 'player_addplayList: bal set_selectindex(the play position)'),
    (0x479910, 0x0320f809, 'Add to playlist: jalr player_addplayList'), (0x479918, 0x2403fffb, 'Add to playlist: -5 is the message, the sheet stays'),
    (0x479954, 0x3c050002, 'Add to playlist: the context is 0x2f001 (lui 2)'), (0x47995c, 0x34a5f001, 'Add to playlist: the context is 0x2f001 (ori 0xf001)'),
    (0x479968, 0x0320f809, 'Add to playlist: jalr navigator_to_with_context("playlist_page", 0x2f001)'),
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
    # why a restacked Sleep Timer page of ours needs no refresh from pm_on_sleep: stock's restack delivers EVT_WINDOW_TO_FG to it, and our page's own handler (patch/m1plus.c page_refresh) re-reads the state
    (0x6789e8, 0x2405012d, 'window_manager_switch_to (animation 0): a1 = EVT_WINDOW_TO_FG 0x12d ...'), (0x6789f4, 0x0411ff88, '... window_manager_dispatch_window_event(new window, 0x12d)'),
)
PULLDOWN_OPEN_SITES = (0x4cd894, 0x4cd8bc)
PULLDOWN_DIALOG_SITE = 0x4cd864   # on_wm_tsmove_fun: the `bal navigator_to` that opens the pull-down dialog (modal: it returns once the dialog is quit)
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
    (PULLDOWN_DIALOG_SITE + 4, 0x24849a4c, 'its delay slot: a0 = "dialog/dropdown_dialog"'),
    # the power key's long press (on_wm_keylong_fun 0x4cdd9c), which the Power Off tile repeats: the two guard words, standby_mode = 1, awake_screen, the msg_poweroff text in a kind 1 context, the modal confirm, Yes (0xa) -> poweroff_page, else standby_mode = 0
    (0x4cddc4, 0x8f91b33c, 'key long press: lw s1, GOT standby_mode (0xa059e0)'), (0x4cddcc, 0x1043002d, 'key long press: standby_mode == 2 returns'), (0x4cddd4, 0x8f84b068, 'key long press: lw a0, GOT 0xa059dc (POWERKEY_BLOCK)'),
    (0x4cdddc, 0x10830029, 'key long press: that word == 2 returns'), (0x4cde0c, 0xae320000, 'key long press: sw s2 (1), (s1): standby_mode = 1'), (0x4cde10, 0x04116502, 'key long press: bal awake_screen (0x4e721c)'),
    (0x4cde3c, 0xafb20018, 'key long press: sw s2 (1), 0x18(sp): the confirm context\'s kind = 1'), (0x4cde30, 0x24060200, 'key long press: a2 = 0x200, the text size'),
    (0x4cde48, 0x0411fb73, 'key long press: bal getFormatString (0x4ccc18)'), (0x4cde4c, 0x24849ae0, 'key long press: a0 = "msg_poweroff"'), (0x4cde60, 0x04110fb9, 'key long press: bal navigator_to_with_context'), (0x4cde64, 0x24844570, 'key long press: a0 = "dialog/confirminfo_dialog"'),
    (0x4cde6c, 0x1443000c, 'key long press: bne v0, 0xa: only Yes goes on'), (0x4cde7c, 0x04110fc0, 'key long press: bal navigator_to'), (0x4cde80, 0x2484412c, 'key long press: a0 = "poweroff_page"'), (0x4cdea4, 0xae200000, 'key long press: sw zero, (s1): standby_mode = 0 after anything but Yes'),
    (0x4cd86c, 0x2403000d, 'on_wm_tsmove_fun: v1 = 0xd, what a tile quits the dialog with'), (0x4cd870, 0x14430014, 'on_wm_tsmove_fun: any other result skips the page opening (bne v0, v1, 0x4cd8c4)'),
    (0x4cd828, 0x8f82a9b4, 'on_wm_tsmove_fun: lw v0, GOT pressdown_y (0xa05a30)'), (0x4cd82c, 0x8c440000, 'on_wm_tsmove_fun: lw a0, (v0): pressdown_y'),
    (0x4cd830, 0x28820051, 'on_wm_tsmove_fun: slti v0, a0, 0x51 (81: row 1 tiles start at y 51, so a hold quit resets pressdown_y >= 81)'), (0x4cd834, 0x10400023, 'on_wm_tsmove_fun: beqz v0, return'),
    (0x4754fc, 0x8f82a960, 'System tile handler 0x4754c8: lw v0, GOT 0xa05a00 (DROPDOWN_BUSY; the Playback handler 0x475558 reads the same word at 0x47558c)'), (0x47558c, 0x8f82a960, 'Playback tile handler: the same word'),
    (0x475518, 0x8f99a968, 'System tile handler: lw t9, GOT airplayGetFlag (0x5cfc4c)'), (0x47552c, 0x8f99a838, 'System tile handler: lw t9, GOT dialog_quit (0x64f378)'),
    (0x475530, 0x2405000d, 'System tile handler: a1 = 0xd'), (0x475534, 0x0320f809, 'System tile handler: jalr dialog_quit(a0 = the handler\'s ctx, the dialog)'),
    (0x4754e8, 0x8f91a96c, 'System tile handler 0x4754c8: lw s1, GOT syssetinto_flag'), (0x4754f4, 0x14400013, 'System tile handler: bnez v0, return (a nonzero flag does nothing)'),
    (0x475578, 0x8f91a95c, 'Playback tile handler 0x475558: lw s1, GOT playsetinto_flag'), (0x475584, 0x14400013, 'Playback tile handler: bnez v0, return'),    # the AirPlay and DLNA tiles call stock's own switches: each flips one setting byte and persists it ([SYSSET] AIRPLAY / DLNA); the network-status timer (0x4cfd94) then starts or stops the service to match
    (0x5076b4, 0x8f82afc0, 'airplay_switch 0x5076a8: lw v0, GOT 0xa05abd (the AirPlay setting byte, AIRPLAY_FLAG)'), (0x5076d0, 0x38840001, 'airplay_switch: xori a0, a0, 1 (flip)'), (0x5076d8, 0xa0440000, 'airplay_switch: sb a0, (v0) (store the byte; the delay slot of the tail call that writes the ini)'),
    (0x507680, 0x8f82afbc, 'dlna_switch 0x507674: lw v0, GOT 0xa05abe (the DLNA setting byte, DLNA_FLAG)'), (0x50769c, 0x38840001, 'dlna_switch: xori a0, a0, 1 (flip)'), (0x5076a4, 0xa0440000, 'dlna_switch: sb a0, (v0) (store the byte; the delay slot of the tail call that writes the ini)'),
    (0x4cfde4, 0x8f99b470, 'on_wm_timer_networkstatus 0x4cfd94: lw t9, GOT airplay_start (0x5076dc), which starts or stops shairport to match the byte'), (0x4cfde8, 0x0320f809, 'on_wm_timer_networkstatus: jalr airplay_start'),
    (0x4cfe18, 0x8f99b474, 'on_wm_timer_networkstatus: lw t9, GOT dmr_serverstart (0x508354), which starts or stops the DLNA renderer to match the byte'), (0x4cfe1c, 0x0320f809, 'on_wm_timer_networkstatus: jalr dmr_serverstart'),
)
# Hook 38: on_wm_idle_status's check_usb_status call (`lw t9, GOT; bal`, nop, `lw gp` after; the result is not read) becomes `jal pd_usb_poll` (patch/pulldown.c, docs/modules/pulldown.md "The USB gate").
# With state 2, no cable and no usbmode_page in the stack it drops the USB page's pending byte and stores 1, so the same call's unplug branch resets it. Every idle pass, from boot: one load, then stock.
USBPOLL_SITE = 0x4cef08
USBPOLL_PINS = (
    (0x4cef04, 0x8f99b430, 'on_wm_idle_status: lw t9, GOT check_usb_status'), (USBPOLL_SITE, 0x0411fcb7, 'on_wm_idle_status: bal check_usb_status (the hook replaces it)'),
    (0x4cef0c, 0x00000000, 'its delay slot: nop'), (0x4cef10, 0x8fbc0010, 'on_wm_idle_status: lw gp after the call (the result is not read)'),
    (0x4ce304, 0x1643000b, 'check_usb_status, cable in: bne s2 (the state), 1: only state 1 asks the host'), (0x4ce310, 0x0320f809, 'jalr toolsGetpclinkStatus'),
    (0x4ce318, 0x1452000d, 'bne v0, s2: no host answer keeps 1 (then 0x4ce324 stores 2 and 0x4ce32c asks for the page)'),
    (0x4ce1e8, 0x3c1c0053, 'check_usb_status prologue (pd_usb_poll calls it)'), (0x4ce1ec, 0x279c5ce8, 'check_usb_status prologue'), (0x4ce1f0, 0x0399e021, 'check_usb_status prologue'),
)
# Hook 39: on_wm_timer_dialogresponse's read of the USB page's pending byte (`lbu v1, 0x41b1(v0)`; `beqz v1, 0x4cf2cc`, delay slot `lw s0, GOT 0xa00000`) becomes `j pod_usb_site; nop`. The stub asks
# pd_usb_take, which drops the request when the cable is gone (and unplugs a state 2 at once through pd_usb_poll), then runs the branch as stock (both paths get s0, and v0 the 0xa00000 page the open path's `sb zero, 0x41b1(v0)` uses). Every timer pass: one load.
USBTAKE_SITE, USBTAKE_OPEN, USBTAKE_SKIP = 0x4cf254, 0x4cf260, 0x4cf2cc
USBTAKE_PINS = (
    (0x4cf1d0, 0x14620020, 'on_wm_timer_dialogresponse: bne v1, v0, 0x4cf254 (the other way to the site)'), (0x4cf1d4, 0x8f8282c0, 'its delay slot: lw v0, GOT 0xa00000'),
    (0x4cf250, 0x8f8282c0, 'lw v0, GOT 0xa00000'), (USBTAKE_SITE, 0x904341b1, 'lbu v1, 0x41b1(v0): the pending byte (the hook replaces it)'),
    (0x4cf258, 0x1060001c, 'beqz v1, 0x4cf2cc: nothing pending (the hook replaces it)'), (0x4cf25c, 0x8f9082c0, 'its delay slot: lw s0, GOT 0xa00000 (the stub runs it on both paths)'),
    (USBTAKE_OPEN, 0x8f99804c, 'the open path: lw t9, GOT window_manager'), (0x4cf264, 0x0320f809, 'jalr window_manager'), (0x4cf268, 0xa04041b1, 'its delay slot: sb zero, 0x41b1(v0): the byte cleared'),
    (0x4cf2bc, 0x04110ab0, 'bal navigator_to'), (0x4cf2c0, 0x24849bf0, 'a0 = "usbmode_page"'), (0x4cf2c4, 0x8fbc0018, 'lw gp, 0x18(sp)'), (0x4cf2c8, 0x8f9082c0, 'lw s0, GOT 0xa00000'),
    (USBTAKE_SKIP, 0x920241b0, 'the next check: lbu v0, 0x41b0(s0) (s0 the page, from either path)'),
)
# The swipe's two gates (docs/modules/pulldown.md "Swipe gates and the window stack"): on_wm_tsmove_fun refuses to open the pull-down while lockscreen_pageflag (0xa059fc) is 1 or dropdown_menu_state (0xa05a2c) is not 0;
# the first is stored only by the lock page's init (1) and its EVT_WINDOW_CLOSE handler (0), the second only by the pull-down's own handlers and tsmove (its 0 by the dialog's EVT_WINDOW_CLOSE handler 0x4750ec).
TSDOWN_PINS = (   # (address, stock word, what it proves)
    (0x4cd728, 0x8f82a9a8, 'on_wm_tsdown_fun 0x4cd6e8: lw v0, GOT dropdown_menu_state (0xa05a2c)'), (0x4cd72c, 0x8c420000, 'on_wm_tsdown_fun: lw v0, (v0): the state'),
    (0x4cd730, 0x10400003, 'on_wm_tsdown_fun: beqz v0, store (state 0 stores pressdown_y)'), (0x4cd738, 0x14430005, 'on_wm_tsdown_fun: bne v0, 3: any state but 0 and 3 skips the store'),
    (0x4cd740, 0x8f82a9b4, 'on_wm_tsdown_fun: lw v0, GOT pressdown_y (0xa05a30)'), (0x4cd744, 0x8ca3001c, 'on_wm_tsdown_fun: lw v1, 0x1c(a1): the event\'s y'),
    (0x4cd748, 0xac430000, 'on_wm_tsdown_fun: sw v1, (v0): pressdown_y = y'),
    (0x4cd7fc, 0x8f82b344, 'on_wm_tsmove_fun: lw v0, GOT lockscreen_pageflag (0xa059fc)'), (0x4cd800, 0x8c430000, 'on_wm_tsmove_fun: lw v1, (v0)'),
    (0x4cd804, 0x24020001, 'on_wm_tsmove_fun: v0 = 1'), (0x4cd808, 0x1062002e, 'on_wm_tsmove_fun: beq v1, 1: the lock flag set returns without opening'),
    (0x4cd818, 0x8f82a9a8, 'on_wm_tsmove_fun: lw v0, GOT dropdown_menu_state'), (0x4cd81c, 0x8c440000, 'on_wm_tsmove_fun: lw a0, (v0)'),
    (0x4cd820, 0x14800028, 'on_wm_tsmove_fun: bnez a0: a nonzero state returns without opening'),
    (0x53fdac, 0x24030001, 'screensaver_page_init: v1 = 1'), (0x53fdbc, 0x8f82b344, 'screensaver_page_init: lw v0, GOT lockscreen_pageflag'),
    (0x53fdc8, 0xac430000, 'screensaver_page_init: sw v1, (v0): the lock flag is set to 1 (its only store of 1)'),
    (0x53f1ac, 0x8f82b344, 'lock page EVT_WINDOW_CLOSE handler 0x53f1a0: lw v0, GOT lockscreen_pageflag'), (0x53f1b0, 0xac400000, 'lock page EVT_WINDOW_CLOSE handler: sw zero, (v0): the only store of 0'),
    (0x4750fc, 0x8f82a9a8, 'dropdown dialog EVT_WINDOW_CLOSE handler 0x4750ec: lw v0, GOT dropdown_menu_state'), (0x475118, 0xac400000, 'dropdown dialog EVT_WINDOW_CLOSE handler: sw zero, (v0): the only store of 0'),
    # the close handler removes only the refresh timer in the global 0x97c750, never the slide timer; the slide callback's last frame stores state 3 with no check that the dialog is closing (m1plus's pd_on_close cancels the slide timer)
    (0x475fb0, 0x24c650ec, 'init: the close handler\'s address, a2 = 0x470000 + 0x50ec (0x4750ec), bound to 0x12e at 0x475f94'),
    (0x475114, 0x8f90a9ac, 'close handler 0x4750ec: lw s0, GOT 0x97c750 (the refresh timer\'s id)'), (0x47511c, 0x8e050000, 'close handler: lw a1, (s0): the id'),
    (0x475124, 0x8f99a85c, 'close handler: lw t9, GOT widget_remove_timer (0x668cb0)'), (0x475128, 0x0320f809, 'close handler: jalr widget_remove_timer: its only timer call'),
    (0x4754bc, 0x24030003, 'slide callback 0x47535c, last opening frame: v1 = 3'), (0x4754c4, 0xac430000, 'slide callback: sw v1, (dropdown_menu_state): state 3, no check that the dialog is closing'),
    (0x47515c, 0x8f99a844, 'pointer-down handler 0x47514c: lw t9, GOT widget_get_prop (0x6676bc)'), (0x475188, 0x26453e98, 'pointer-down handler: a1 = "timer_idex" (0x743e98), the slide timer\'s id property'),
    (0x475184, 0x0320f809, 'pointer-down handler: jalr widget_get_prop(dlg, "timer_idex", &v)'), (0x475194, 0x8f99a854, 'pointer-down handler: lw t9, GOT value_uint32 (0x712380)'),
    (0x4751a4, 0x10430019, 'pointer-down handler: beq v0, -1: no slide timer, nothing to cancel'), (0x4751ac, 0x8f99a858, 'pointer-down handler: lw t9, GOT timer_count (0x6638cc)'),
    (0x4751b8, 0x10400014, 'pointer-down handler: beqz timer_count: no timer, nothing to cancel'),
    (0x4751d4, 0x8f99a85c, 'pointer-down handler: lw t9, GOT widget_remove_timer (0x668cb0)'), (0x4751d8, 0x0320f809, 'pointer-down handler: jalr widget_remove_timer(dlg, id)'),
    (0x4751ec, 0x0320f809, 'pointer-down handler: jalr value_set_uint32(&v, -1)'), (0x475204, 0x0320f809, 'pointer-down handler: jalr widget_set_prop(dlg, "timer_idex", &v)'),
    # the third gate, usblink_status (0xa059f4) 2: written only by check_usb_status (0, 1, 2) and usbmode_exit (3); pd_usb_poll stores 1 for a stale 2 so the idle poll's own unplug branch runs
    (0x4cd7a4, 0x24100002, 'on_wm_tsmove_fun: s0 = 2'), (0x4cd7d0, 0x8f82a964, 'on_wm_tsmove_fun: lw v0, GOT usblink_status'), (0x4cd7d4, 0x8c420000, 'on_wm_tsmove_fun: lw v0, (v0)'),
    (0x4cd7d8, 0x1050003a, 'on_wm_tsmove_fun: beq v0, s0: only state 2 returns without opening'),
    (0x4ce228, 0x8f82a910, 'check_usb_status 0x4ce1e8: lw v0, GOT usbdet_value (0xa059f8, POWER_EXT)'), (0x4ce230, 0x14640047, 'check_usb_status: bne v1, 1: no cable goes to the unplug branch 0x4ce350'),
    (0x4ce320, 0x24030002, 'check_usb_status: v1 = 2 (the host answered)'), (0x4ce324, 0xae230000, 'check_usb_status: sw v1, usblink_status'), (0x4ce32c, 0xa06241b1, 'check_usb_status: sb v0 (1), 0xa041b1: the USB page pending'),
    (0x4ce350, 0x8e020000, 'check_usb_status unplug: lw v0, usbdet_value'), (0x4ce354, 0x1440ffb2, 'check_usb_status unplug: bnez: a cable returns'),
    (0x4ce364, 0x7c110844, 'check_usb_status unplug: ins s1, zero, 1, 1 (state & ~2)'), (0x4ce368, 0x1622fff2, 'check_usb_status unplug: bne s1, 1: only states 1 and 3 are reset (2 is skipped)'),
    (0x4ce380, 0x14510006, 'check_usb_status unplug: bne v0, s1: only state 1 runs storage_config.sh stop'), (0x4ce394, 0x24849b50, 'check_usb_status unplug: a0 = "storage_config.sh stop"'),
    (0x4ce3a4, 0x0320f809, 'check_usb_status unplug: jalr toolsSetpclinkStatus(0)'), (0x4ce3a8, 0xae000000, 'check_usb_status unplug: sw zero, usblink_status'),
    (0x545800, 0x8f82a964, 'usbmode_exit: lw v0, GOT usblink_status'), (0x545804, 0x24030003, 'usbmode_exit: v1 = 3'), (0x545808, 0xac430000, 'usbmode_exit: sw v1: its only store, 3'),
)
TSDOWN_PROLOGUE = (0x3c1c0053, 0x279c67e8, 0x0399e021)   # on_wm_tsdown_fun's PIC prologue (lui gp, 0x53; addiu gp, gp, 0x67e8; addu gp, gp, t9)

# Settings > General > Language (patch/language.c, docs/modules/language.md): stock's row handler of systemset/language_page (0x4a7cb0, bound to each of its 13 rows by the init 0x4a80b0): the word is stored,
# [SYSSET] LANGUAGE saved, switch_language(word) loads the locale (the window manager re-translates every open window and our font forms follow EVT_LOCALE_CHANGED), then change_lanflag = 1,
# homemenu_changeflag = 2 and navigator_back_to_home(): the Home foreground callback 0x534858 resets the menu index and rebuilds the menu in the new language. The same word is nothing.
LANGUAGE_PINS = (   # (address, stock word, what it proves)
    (0x4a7cf0, 0x8f92afa4, 'row handler 0x4a7cb0: lw s2, GOT language (0xa05ab8)'),
    (0x4a7d00, 0x8e540000, 'row handler: lw s4, (s2): the current word'),
    (0x4a7d04, 0x1282004d, "row handler: beq s4, v0 (the row's number): the same language does nothing"),
    (0x4a7df8, 0x24c64918, 'row handler: a2 = "LANGUAGE"'),
    (0x4a7dfc, 0xae500000, 'row handler: sw s0, (s2): the word is stored first'),
    (0x4a7e00, 0x0320f809, 'row handler: jalr write_int_config(word, "SYSSET", "LANGUAGE")'),
    (0x4a7e04, 0x24a54540, 'row handler: a1 = "SYSSET" (the delay slot)'),
    (0x4a7e0c, 0x8f99afa8, 'row handler: lw t9, GOT switch_language'),
    (0x4a7e10, 0x0320f809, 'row handler: jalr switch_language(word)'),
    (0x4a7e14, 0x8e440000, 'row handler: a0 = the stored word (the delay slot)'),
    (0x4a7e18, 0x24030001, 'row handler: v1 = 1'),
    (0x4a7e20, 0x8f82afac, 'row handler: lw v0, GOT change_lanflag (0xa05a39)'),
    (0x4a7e28, 0xa0430000, 'row handler: sb 1, change_lanflag'),
    (0x4a7e2c, 0x24030002, 'row handler: v1 = 2'),
    (0x4a7e30, 0x8f82aa18, 'row handler: lw v0, GOT homemenu_changeflag (0xa05a50)'),
    (0x4a7e34, 0x0320f809, 'row handler: jalr navigator_back_to_home (the last call)'),
    (0x4a7e38, 0xac430000, 'row handler: sw 2, homemenu_changeflag (the delay slot: stored before the call)'),
    (0x4cca54, 0x2484ffff, 'switch_language: a0 - 1'),
    (0x4cca5c, 0x2c82000c, 'switch_language: sltiu a0, 12: the words 1 .. 12 index the locale table'),
    (0x4cca64, 0x10400009, 'switch_language: anything else loads zh_CN (the default)'),
    (0x4cca90, 0x24849998, 'switch_language default: a0 = "zh_CN"'),
    (0x4d20bc, 0x0320f809, 'navigator_back_to_home: jalr window_manager'),
    (0x4d20d0, 0x8f99b6b4, 'navigator_back_to_home: lw t9, GOT window_manager_back_to_home'),
    (0x4d20d4, 0x03200008, 'navigator_back_to_home: jr t9 (a tail call)'),
    (0x534888, 0x8f93afac, 'Home foreground callback 0x534858: lw s3, GOT change_lanflag'),
    (0x53488c, 0x92620000, 'Home callback: lbu v0, (s3)'),
    (0x534890, 0x10400008, 'Home callback: beqz v0: no language change'),
    (0x534898, 0x8f99aa2c, 'Home callback: lw t9, GOT reset_homemenu_index'),
    (0x5348a0, 0x24040001, 'Home callback: reset_homemenu_index(1)'),
    (0x5348a4, 0x24020002, 'Home callback: v0 = 2'),
    (0x5348ac, 0xae420000, 'Home callback: sw 2, homemenu_changeflag'),
    (0x5348b0, 0xa2600000, 'Home callback: sb zero, change_lanflag'),
    (0x4e6528, 0x8f83afa4, 'config_init: lw v1, GOT language'),
    (0x4e6534, 0xac620000, 'config_init: sw v0, (v1): the word is atoi of [SYSSET] LANGUAGE, not clamped'),
    (0x744918, 0x474e414c, 'the string "LANG(UAGE)"'),
    (0x74491c, 0x45474155, 'the string "(LANG)UAGE"'),
    (0x97c880, 0x00747fb4, "language page's key table 0x97c880: row 0"),
    (0x97c884, 0x00747fc4, "language page's key table 0x97c880: row 1"),
    (0x97c888, 0x00747fd4, "language page's key table 0x97c880: row 2"),
    (0x97c88c, 0x00747fe0, "language page's key table 0x97c880: row 3"),
    (0x97c890, 0x00747ff0, "language page's key table 0x97c880: row 4"),
    (0x97c894, 0x00747ffc, "language page's key table 0x97c880: row 5"),
    (0x97c898, 0x00748008, "language page's key table 0x97c880: row 6"),
    (0x97c89c, 0x00748014, "language page's key table 0x97c880: row 7"),
    (0x97c8a0, 0x00748020, "language page's key table 0x97c880: row 8"),
    (0x97c8a4, 0x0074802c, "language page's key table 0x97c880: row 9"),
    (0x97c8a8, 0x00748038, "language page's key table 0x97c880: row 10"),
    (0x97c8ac, 0x00748044, "language page's key table 0x97c880: row 11"),
    (0x97c8b0, 0x00748050, "language page's key table 0x97c880: row 12"),
)
# Settings > General > Date & Time (patch/datetime.c, docs/modules/datetime.md): the three stock pages behind System list row 5 (system_time). typedatetime_page (init 0x4aed58) holds the Auto row
# (-> autosynctime_page), the Manual row (-> datetime_page; disabled while auto time is on, 0x4aec74) and the 24-hour switch 0x4aeb50. autosynctime_page's click handler 0x4a25b8 is the switch (row 0) and
# the zone rows (row n is the zone n - 2); its page builder 0x4a2424 makes the zone rows only while auto time is ON (movz at 0x4a2474: the byte 0 leaves the one switch row). datetime_page's confirm 0x4a576c
# reads the five selectors and calls set_systime, then navigator_back.
DATETIME_PINS = (   # (address, stock word, what it proves)
    (0x4a2468, 0x90530000, 'zone page builder 0x4a2424: lbu s3, (auto_sync_nettime)'), (0x4a2474, 0x0073100a, 'zone page builder: movz v0, v1 (1), s3: auto time off leaves the one switch row; on shows the zone rows'),
    (0x4a2610, 0x14400020, 'zone page click 0x4a25b8: bnez row, 0x4a2694: row 0 is the switch'), (0x4a2618, 0x8f83aea8, 'auto switch: lw v1, GOT auto_sync_nettime'), (0x4a261c, 0x90640000, 'auto switch: lbu a0, (v1)'),
    (0x4a2620, 0x10800018, 'auto switch: beqz a0: from off'), (0x4a2624, 0x8f82aebc, 'auto switch: lw v0, GOT sync_nettime_flag'), (0x4a2628, 0xa0400000, 'auto switch, from on: sb zero, (v0): no sync wanted'),
    (0x4a262c, 0xa0600000, 'auto switch, from on: sb zero, (v1): the byte off'), (0x4a2640, 0x24c67a2c, 'auto switch: a2 = "AUTOSYNCTIME"'), (0x4a2644, 0x0320f809, 'auto switch: jalr write_int_config(byte, "SYSSET", ...)'),
    (0x4a2648, 0x24a54540, 'auto switch: a1 = "SYSSET"'), (0x4a2684, 0x24040001, 'auto switch, from off: a0 = 1'), (0x4a2688, 0xa0440000, 'auto switch, from off: sb a0, (v0): a sync is wanted (networktime_adjust_thd runs it)'),
    (0x4a2690, 0xa0640000, 'auto switch, from off: sb a0, (v1): the byte on, in the delay slot of the branch back to the save'),
    (0x4a269c, 0x2450fffe, 'zone click: s0 = row - 2'), (0x4a26a4, 0x1290ffee, 'zone click: beq s4, s0: the zone that is chosen already does nothing'), (0x4a2790, 0x24c67a3c, 'zone click: a2 = "TIMEZONE"'),
    (0x4a2794, 0xae700000, 'zone click: sw s0, (time_zone) in the delay slot of the save: the word first'), (0x4a2798, 0x0320f809, 'zone click: jalr write_int_config(index, "SYSSET", "TIMEZONE")'),
    (0x4a279c, 0x24a54540, 'zone click: a1 = "SYSSET"'),
    (0x4aeb74, 0x8f91b094, '24-hour switch 0x4aeb50: lw s1, GOT time24hflag'), (0x4aeb80, 0x38440001, '24-hour switch: xori a0, v0, 1'), (0x4aeb84, 0x0320f809, '24-hour switch: jalr change_time24h_12h(new)'),
    (0x4aeb88, 0xa2240000, '24-hour switch: sb a0, (s1) in the delay slot: the byte first'), (0x4aeba0, 0x24c68c54, '24-hour switch: a2 = "TIME24H"'), (0x4aeba4, 0x0320f809, '24-hour switch: jalr write_int_config(byte, "SYSSET", "TIME24H")'),
    (0x4aeba8, 0x24a54540, '24-hour switch: a1 = "SYSSET"'),
    (0x4e6648, 0x2c430002, 'config_init: TIME24H sltiu v1, v0, 2'), (0x4e664c, 0x0043200b, 'config_init: movn a0, v0, v1: 0 and 1 kept, else 1'),
    (0x4aec74, 0x8f82aea8, 'Manual row refresh 0x4aebd8: lw v0, GOT auto_sync_nettime'), (0x4aec7c, 0x10400017, 'Manual row refresh: beqz: the row is enabled only while auto time is off'),
    (0x4a5970, 0x0320f809, 'manual time page init 0x4a58fc: jalr get_systime(&minute, &hour, &day, &month, &year)'), (0x4a5aa8, 0x240507e6, 'manual time page: a1 = 2022 (the year selector clamp)'),
    (0x4a5aac, 0x2c42001d, 'manual time page: sltiu v0, v0, 29: 2022 .. 2050 kept, else 2022'), (0x4a5acc, 0x2ca5000c, 'manual time page: sltiu a1, a1, 12 (month - 1)'), (0x4a5aec, 0x2ca5001f, 'manual time page: sltiu a1, a1, 31 (day - 1)'),
    (0x4a58c0, 0x8fa60024, 'confirm 0x4a576c: a2 = the day selector'), (0x4a58cc, 0x0320f809, 'confirm: jalr set_systime(year, month, day, hour, minute): the call that sets the clock'), (0x4a58d8, 0x8f99aad8, 'confirm: t9 = navigator_back (0x4d20dc)'),
    (0x4a58f4, 0x03200008, 'confirm: jr t9: navigator_back'), (0x4d7728, 0x8fa2001c, 'get_systime: the minute from the tm'), (0x4d7770, 0x3c1c0053, 'set_systime 0x4d7770: PIC prologue'),
    (0x4d77bc, 0x8f99b770, 'set_systime: lw t9, GOT toolsSetRtcTime'), (0x4d77cc, 0x0320f809, 'set_systime: jalr toolsSetRtcTime(0, minute, hour, day, month, year): date -s, then hwclock -w(u)'),
)
# Sleep Timer (patch/sleeptimer.c, docs/modules/sleeptimer.md): systemset/powermanager_page's view_sleep as its handlers write it. The switch 0x4a9ae0 xors the byte sleepflag and stores 0 in the word sleep_time (in the delay
# slot of the refresh 0x4a9924), saving nothing and calling no timer reset; Back (0x4a91d0) and the top-right Now Playing button (0x4a8d98) store (hour * 60 + minute) * 60 from the two selectors (hours 0 .. 3, minutes
# 0 .. 59: the options set at 0x4a8f84 / 0x4a8ffc) and save nothing either. The countdown (to_poweroptions's tail, 0x4ce784): while the byte is set and the word is above 0, one is taken per tick; at 0 the byte is
# cleared and poweroff_page opens. So the word is the count left, not the time that was chosen. The refresh shows the selectors from the word (hours = word / 3600, minutes = word % 3600 / 60).
SLEEPTIMER_PINS = (   # (address, stock word, what it proves)
    (0x4a9af0, 0x8f83afe0, 'sleep switch 0x4a9ae0: lw v1, GOT sleepflag (0xa05a94)'), (0x4a9b00, 0x90620000, 'sleep switch: lbu v0, (v1)'), (0x4a9b08, 0x38420001, 'sleep switch: xori v0, v0, 1'),
    (0x4a9b0c, 0xa0620000, 'sleep switch: sb v0, (v1): the byte first'), (0x4a9b10, 0x8f82afd0, 'sleep switch: lw v0, GOT sleep_time (0xa05a90)'), (0x4a9b14, 0x0411ff83, 'sleep switch: bal refresh 0x4a9924'),
    (0x4a9b18, 0xac400000, 'sleep switch: sw zero, (v0): the word 0 in the refresh call\'s slot (no save, no reset_poweroptions_timer call anywhere in the handler)'),
    (0x4a9258, 0x2403003c, 'Back 0x4a91d0: v1 = 60'), (0x4a9260, 0x72032002, 'Back: mul a0, s0, v1 (the hour selector * 60)'), (0x4a9268, 0x00821021, 'Back: addu v0, a0, v0 (+ the minute selector)'),
    (0x4a926c, 0x70431002, 'Back: mul v0, v0, v1 (* 60: seconds)'), (0x4a9270, 0x8f83afd0, 'Back: lw v1, GOT sleep_time'), (0x4a9274, 0xac620000, 'Back: sw v0, (v1): the one store, whatever the byte is'),
    (0x4a9264, 0x8f99aad8, 'Back: lw t9, GOT navigator_back (the tail call: no save)'), (0x4a9284, 0x03200008, 'Back: jr t9 (navigator_back)'),
    (0x4a8f84, 0x24050003, 'page init walk: the hour selector\'s options end at 3 (hours 0 .. 3)'), (0x4a8ffc, 0x2405003b, 'page init walk: the minute selector\'s options end at 59'),
    (0x4a99ec, 0x8f82afe0, 'refresh 0x4a9924: lw v0, GOT sleepflag'), (0x4a99f0, 0x90420000, 'refresh: lbu v0, (v0)'), (0x4a99f4, 0x1040002a, 'refresh: beqz: a zero byte is off (anything else is on)'),
    (0x4a9a34, 0x24050e10, 'refresh: a1 = 3600 (hours = the word / 3600)'), (0x4a9a40, 0x8f82afd0, 'refresh: lw v0, GOT sleep_time'),
    (0x4ce784, 0x8f83afe0, 'countdown (to_poweroptions tail): lw v1, GOT sleepflag'), (0x4ce788, 0x90620000, 'countdown: lbu v0, (v1)'), (0x4ce78c, 0x1040000d, 'countdown: beqz: nothing while the byte is 0'),
    (0x4ce794, 0x8f84afd0, 'countdown: lw a0, GOT sleep_time'), (0x4ce798, 0x8c820000, 'countdown: lw v0, (a0)'), (0x4ce79c, 0x18400009, 'countdown: blez: nothing while the word is 0'),
    (0x4ce7a0, 0x2442ffff, 'countdown: addiu v0, v0, -1 (one per tick)'), (0x4ce7a4, 0x14400006, 'countdown: bnez: not yet 0'), (0x4ce7a8, 0xac820000, 'countdown: sw v0, (a0)'),
    (0x4ce7b4, 0xa0600000, 'countdown: sb zero, (v1): at 0 the byte is cleared'), (0x4ce7b8, 0x04110d71, 'countdown: bal navigator_to("poweroff_page")'),
)
# Network Services and Wi-Fi Transfer (patch/netservice.c, docs/modules/wifi-transfer.md): systemset/netservice_page and systemset/wifitransport_page as stock's code does them. The three rows' handlers
# (listitem0 DLNA 0x4a8b14, listitem1 AirPlay 0x4a8a84, listitem2 Wi-Fi transfer 0x4a8c2c, bound at 0x4a8920 / 0x4a8954 / 0x4a8980): the two switches look up their image, call dlna_switch / airplay_switch with no
# test in between (only the lookup's null check) and show the byte; the third asks networkGetConnectStatus (nonzero: navigator_to the transfer page). The transfer page's init (0x4b1664) asks networkGetIPAddr,
# stop_player and switch_wifitransport(1) (0x5075e4: toolsSystemd "thttpd -C /etc/thttpd.conf", the byte wifitransport_flag 0xa05abc = 1; with 0: "killall -9 thttpd", remove the log and the pid file, the byte 0),
# prints "http://%s:8888", and binds the window's EVT_KEY_UP (0x113: 0x4b14d0 answers RET_STOP for the keys 0xd5 .. 0xd7 and RET_OK for any other) and EVT_WINDOW_CLOSE (0x12e: 0x4b14ec calls switch_wifitransport(0)). The byte
# is read by the pull-down gate (on_wm_tsmove_fun) and by the standby / shutdown countdown (to_poweroptions), which do nothing while it is set. Nothing else calls switch_wifitransport.
NETSERVICE_PINS = (   # (address, stock word, what it proves)
    (0x4a8920, 0x24c68b14, 'netservice_page: listitem0 (DLNA) click = 0x4a8b14'), (0x4a8954, 0x24c68a84, 'netservice_page: listitem1 (AirPlay) click = 0x4a8a84'), (0x4a8980, 0x24c68c2c, 'netservice_page: listitem2 (Wi-Fi transfer) click = 0x4a8c2c'),
    (0x4a8abc, 0x1080000f, 'AirPlay click 0x4a8a84: beqz a0: the only test, the image lookup'), (0x4a8ac4, 0x8f99afc4, 'AirPlay click: lw t9, GOT airplay_switch'), (0x4a8ac8, 0x0320f809, 'AirPlay click: jalr airplay_switch'),
    (0x4a8ad8, 0x8f82afc0, 'AirPlay click: lw v0, GOT airplayflag: the image follows the byte'),
    (0x4a8b4c, 0x1080000f, 'DLNA click 0x4a8b14: beqz a0: the only test, the image lookup'), (0x4a8b54, 0x8f99afc8, 'DLNA click: lw t9, GOT dlna_switch'), (0x4a8b58, 0x0320f809, 'DLNA click: jalr dlna_switch'),
    (0x4a8c48, 0x0320f809, 'Wi-Fi transfer click 0x4a8c2c: jalr networkGetConnectStatus'), (0x4a8c50, 0x14400009, 'Wi-Fi transfer click: bnez: a nonzero status goes on to navigator_to'), (0x4a8c80, 0x0320f809, 'Wi-Fi transfer click: jalr navigator_to("systemset/wifitransport_page")'),
    (0x4b1710, 0x0320f809, 'transfer init 0x4b1664: jalr networkGetIPAddr(0, buf)'), (0x4b1720, 0x0320f809, 'transfer init: jalr stop_player'), (0x4b172c, 0x8f99b0f4, 'transfer init: lw t9, GOT switch_wifitransport'),
    (0x4b1730, 0x0320f809, 'transfer init: jalr switch_wifitransport'), (0x4b1734, 0x24040001, 'transfer init: a0 = 1 in the delay slot'), (0x4b1794, 0x24c68f6c, 'transfer init: a2 = "http://%s:8888"'), (0x748f6c, 0x70747468, 'the format string starts "http"'),
    (0x4b16ac, 0x24050113, 'transfer init: widget_on(window, 0x113 EVT_KEY_UP, ...)'), (0x4b16c8, 0x24c614d0, 'transfer init: ... the key filter 0x4b14d0'), (0x4b16cc, 0x2405012e, 'transfer init: widget_on(window, 0x12e EVT_WINDOW_CLOSE, ...)'),
    (0x4b16e8, 0x24c614ec, 'transfer init: ... the close handler 0x4b14ec'),
    (0x4b14d4, 0x2403000b, 'key filter: v1 = RET_STOP'), (0x4b14d8, 0x2442ff2b, 'key filter: v0 = key code - 0xd5'), (0x4b14dc, 0x2c420003, 'key filter: sltiu v0, v0, 3'), (0x4b14e0, 0x0002180a, 'key filter: movz v1, zero, v0: RET_OK unless the key is 0xd5 .. 0xd7'),
    (0x4b14fc, 0x8f99b0f4, 'close handler 0x4b14ec: lw t9, GOT switch_wifitransport'), (0x4b1508, 0x0320f809, 'close handler: jalr switch_wifitransport'), (0x4b150c, 0x00002025, 'close handler: a0 = 0 in the delay slot'),
    (0x507600, 0x1080000c, 'switch_wifitransport 0x5075e4: beqz a0: 0 stops'), (0x507604, 0x8f90b340, 'switch_wifitransport: lw s0, GOT wifitransport_flag (0xa05abc)'), (0x507610, 0x0320f809, 'switch_wifitransport: jalr toolsSystemd'),
    (0x507614, 0x2484e9c4, 'switch_wifitransport: a0 = "thttpd -C /etc/thttpd.conf"'), (0x50761c, 0xa2020000, 'switch_wifitransport: sb v0, (s0): the byte 1'), (0x507640, 0x2484e9e0, 'switch_wifitransport: a0 = "killall -9 thttpd"'),
    (0x507650, 0x0320f809, 'switch_wifitransport: jalr remove (the log)'), (0x507670, 0xa2000000, 'switch_wifitransport: sb zero, (s0): the byte 0'),
    (0x4cd7f0, 0x8f82b340, 'on_wm_tsmove_fun: lw v0, GOT wifitransport_flag'), (0x4cd7f8, 0x14400032, 'on_wm_tsmove_fun: bnez: no pull-down while the byte is set'),
    (0x4ce668, 0x8f82b340, 'to_poweroptions: lw v0, GOT wifitransport_flag'), (0x4ce670, 0x1440001a, 'to_poweroptions: bnez: no countdown while the byte is set'),
)

# Settings > Library > Update Library (patch/libupdate.c, docs/modules/libupdate.md): systemset/updatemusic_page as stock's code does it, and the scan dialog's finish. Update Now (0x4af070) is
# navigator_to_with_context("dialog/scanmusic_dialog", a context of four zero words); Auto Update (0x4af0bc) stores byte ^ 1 in autoscan_flag (0xa05aa9, in the delay slot of write_int_config) and swaps the
# switch image; Choose Folders (0x4af1f4) asks toolsCheckMount("/mnt/mmc"): nonzero navigator_to("systemset/specfolder_page"), else getFormatString("msg_nottf") in a msginfo context (kind 1, 2000 ms, the text).
# The dialog's timer callback (0x47bab0) calls the refresh 0x47b604 with done = 1 at the first tick that sees the state word 0xa03a40 above 0 (state 1; the call is `bal` at LIBUPDATE_SITE, a0 = the
# dialog in its delay slot), then adds 1 (2: one more finished tick; 3: the dialog quits, 0x47bb04). The workers (0x47b410 full, 0x47b470 folders) store 1 when the scan returns, cancelled or not; Cancel (0x47b5ac)
# calls toolsStopUpdateMusic (the byte 0xa0b088 = 1) while the state is below 3; toolsGetUserStop reads that byte; the dialog's init (0x47bba8) clears the byte (toolsClearDbCount, 0x5efcfc) and the state (0x47bca0).
LIBUPDATE_SITE = 0x47baec   # the dialog timer's `bal 0x47b604` (done = 1) becomes jal lu_scan_finish (patch/libupdate.c, docs/modules/payload.md hook 34)
LIBUPDATE_COMMIT_SITES = (0x4e9e70, 0x4e9f9c)   # scanAllMusicFile's and scanSpecFolder's `jalr t9` (toolsDatabaseCommit) become jal lu_commit (docs/modules/payload.md hook 34)
LIBUPDATE_BATCH_SITE = 0x5ee090   # toolsInsertDbTable's batch COMMIT (every 100 rows inside a scan): its `jalr t9` (sqlite3_exec) becomes jal lu_batch_exec (docs/modules/payload.md hook 34)
LIBUPDATE_PINS = (   # (address, stock word, what it proves)
    (0x4af070, 0x3c1c0055, 'Update Now 0x4af070: prologue'), (0x4af090, 0x248488a4, 'Update Now: a0 = "dialog/scanmusic_dialog"'), (0x4af098, 0xafa00018, 'Update Now: context word 0 = 0'),
    (0x4af09c, 0xafa0001c, 'Update Now: context word 1 = 0'), (0x4af0a0, 0xafa00020, 'Update Now: context word 2 = 0'), (0x4af0a4, 0x0320f809, 'Update Now: jalr navigator_to_with_context'),
    (0x4af0a8, 0xafa00024, 'Update Now: context word 3 = 0 (delay slot)'), (0x4af084, 0x27a50018, 'Update Now: a1 = the context'),
    (0x4af0f0, 0x8f90b09c, 'Auto Update 0x4af0bc: lw s0, GOT autoscan_flag (0xa05aa9)'), (0x4af0f8, 0x92020000, 'Auto Update: lbu v0, (s0)'), (0x4af0fc, 0x38440001, 'Auto Update: xori a0, v0, 1'),
    (0x4af100, 0x0320f809, 'Auto Update: jalr write_int_config("SYSSET", "AUTOSCAN")'), (0x4af104, 0xa2040000, 'Auto Update: sb a0, (s0) (the byte, in the delay slot)'), (0x4af0dc, 0x24c68cf4, 'Auto Update: a2 = "AUTOSCAN"'),
    (0x4af1f4, 0x3c1c0055, 'Choose Folders 0x4af1f4: prologue'), (0x4af214, 0x0320f809, 'Choose Folders: jalr toolsCheckMount'), (0x4af218, 0x24844bd0, 'Choose Folders: a0 = "/mnt/mmc"'),
    (0x4af21c, 0x14400009, 'Choose Folders: bnez: a mounted card goes on to navigator_to'), (0x4af1c4, 0x04117694, 'Choose Folders: bal getFormatString'), (0x4af1c8, 0x24844bdc, 'Choose Folders: a0 = "msg_nottf"'),
    (0x4af1dc, 0x0320f809, 'Choose Folders: jalr navigator_to_with_context(msginfo)'), (0x4af1e0, 0x248445c4, 'Choose Folders: a0 = "dialog/msginfo_dialog"'),
    (0x4af24c, 0x0320f809, 'Choose Folders: jalr navigator_to'), (0x4af250, 0x24848d00, 'Choose Folders: a0 = "systemset/specfolder_page"'),
    (0x47bad0, 0x2739b604, 'scan timer 0x47bab0: t9 = 0x47b604 (the refresh)'), (0x47badc, 0x8e223a40, 'scan timer: lw v0, state'), (0x47bae0, 0x18400026, 'scan timer: blez: still scanning'),
    (0x47bae8, 0x24050001, 'scan timer: a1 = 1 (done)'), (LIBUPDATE_SITE, 0x0411fec5, 'scan timer: bal 0x47b604 (the finish refresh)'), (0x47baf0, 0x02002025, 'scan timer: a0 = the dialog (delay slot)'),
    (0x47baf4, 0x8e223a40, 'scan timer: lw v0, state'), (0x47bafc, 0x24420001, 'scan timer: state + 1'), (0x47bb00, 0xae223a40, 'scan timer: sw state'), (0x47bb04, 0x28420003, 'scan timer: slti v0, 3'),
    (0x47bb80, 0x0411fea0, 'scan timer: bal 0x47b604 with a1 = 0 (still scanning; not hooked)'), (0x47b604, 0x3c1c0059, 'refresh 0x47b604: prologue'), (0x47b608, 0x279c88cc, 'refresh: prologue'),
    (0x47b60c, 0x0399e021, 'refresh: prologue'), (0x47b6d4, 0x0320f809, 'refresh: jalr widget_set_tr_text("scaning_finish") when done'),
    (0x47b460, 0xac433a40, 'full-scan worker 0x47b410: state = 1 when scanAllMusicFile returns'), (0x47b4c0, 0xac433a40, 'folder-scan worker 0x47b470: state = 1 when scanSpecFolder returns'),
    (0x47b42c, 0x0320f809, 'full-scan worker: jalr toolsGetUserStop'), (0x47b448, 0x0320f809, 'full-scan worker: jalr scanAllMusicFile("/mnt/mmc", 1)'), (0x47b4a8, 0x0320f809, 'folder-scan worker: jalr scanSpecFolder(list, 0)'),
    (0x47b5c8, 0x8c423a40, 'Cancel 0x47b5ac: lw v0, state'), (0x47b5cc, 0x28420003, 'Cancel: slti v0, 3'), (0x47b5d0, 0x14400008, 'Cancel: below 3 stops the scan, else quits'),
    (0x5ed944, 0x8f8280b4, 'toolsStopUpdateMusic 0x5ed938: lw v0, GOT'), (0x5ed950, 0xa043b088, 'toolsStopUpdateMusic: sb 1, the stop byte 0xa0b088'), (0x5ed968, 0x9042b088, 'toolsGetUserStop 0x5ed954: lbu the stop byte'),
    (0x5efcfc, 0xa040b088, 'toolsClearDbCount: the stop byte = 0'), (0x47bca0, 0xac403a40, 'scan dialog init: state = 0'),
    (0x4e9e3c, 0x1443000e, 'scanAllMusicFile 0x4e9df4: bne v0, 1: a failed toolsInitDatabase skips the scan and the commit'), (0x4e9ee4, 0x1443002f, 'scanSpecFolder 0x4e9e90: bne v0, 1: the same'),
    (0x4e9e6c, 0x8f99ba54, 'scanAllMusicFile: t9 = toolsDatabaseCommit (GOT)'), (0x4e9e70, 0x0320f809, 'scanAllMusicFile: jalr toolsDatabaseCommit (the site)'), (0x4e9e74, 0, 'scanAllMusicFile: nop (delay slot)'),
    (0x4e9f98, 0x8f99ba54, 'scanSpecFolder: t9 = toolsDatabaseCommit (GOT)'), (0x4e9f9c, 0x0320f809, 'scanSpecFolder: jalr toolsDatabaseCommit (the site)'), (0x4e9fa0, 0, 'scanSpecFolder: nop (delay slot)'),
    (0x5ed990, 0x8e22b080, 'toolsDatabaseCommit 0x5ed96c: lw v0, the transaction word 0xa0b080'), (0x5ed994, 0x1840000c, 'toolsDatabaseCommit: blez v0: no COMMIT while the word is 0'),
    (0x5ed9ac, 0x8e04ac74, 'toolsDatabaseCommit: a0 = the handle 0xa0ac74'), (0x5ed9b4, 0x24a57c9c, 'toolsDatabaseCommit: a1 = "COMMIT;"'), (0x757c9c, 0x4d4d4f43, 'the string starts "COMM"'),
    (0x5ed9b8, 0x0320f809, 'toolsDatabaseCommit: jalr sqlite3_exec (result dropped)'), (0x5ed9c4, 0xae20b080, 'toolsDatabaseCommit: the transaction word = 0'),
    (0x5ed9dc, 0xae00ac74, 'toolsDatabaseCommit: the handle = 0 after sqlite3_close'), (0x5ee038, 0x8e22b080, 'the insert path: lw the transaction word'), (0x5ee044, 0xae22b080, 'the insert path: sw word + 1 (rows since the last COMMIT)'),
    (0x5ee070, 0x8f99f944, 'toolsInsertDbTable 0x5ee2fc: t9 = sqlite3_exec (GOT)'), (0x5ee084, 0xafa20010, 'insert path batch COMMIT: the fifth argument (errmsg) on the stack, 0x10($sp)'), (0x5ee08c, 0x24a57c9c, 'insert path batch COMMIT: a1 = "COMMIT;"'),
    (LIBUPDATE_BATCH_SITE, 0x0320f809, 'insert path batch COMMIT: jalr sqlite3_exec (result dropped; the site)'), (0x5ee094, 0, 'insert path batch COMMIT: nop (delay slot)'), (0x5ee098, 0xae20b080, 'insert path batch COMMIT: the transaction word = 0'),
    (0x5e25b0, 0x3c1c0042, 'toolsCheckMount 0x5e25b0: prologue'), (0x5efb68, 0x3c1c0041, 'toolsGetDbTableNumber 0x5efb68: prologue'), (0x5efb6c, 0x279c4368, 'toolsGetDbTableNumber: prologue'),
    (0x758010, 0x656c6573, 'toolsGetDbTableNumber: the format starts "sele" ("select count(1) from %s")'), (0x4ee0c0, 0x0320f809, 'stock calls toolsGetDbTableNumber(table, "/mnt/data/database.db")'),
)

# Settings > Bluetooth (patch/btset.c, docs/modules/bluetooth.md "Control layer"): every stock sequence the control layer repeats, as runs of consecutive words (the stock handler's own code, so a different demo fails
# the build). 0x4a3b64 is stock's `beqz` here (tools/coex.py turns it into a branch later in the build: Wi-Fi stays on; test/pod/btset.py checks the built demo); the codec table 0x97ca08 holds the eight tr keys get_bluetoothcoding_text copies.
BLUETOOTH_RUNS = (   # (first address, what the words prove, the stock words from there on; one word each, 4 bytes apart)
    (0x4a3abc, 'row handler 0x4a3a7c: the init guard (bt_initstatus != 0) and the row number (atoi)',
     (0x8f82a878, 0x8c420000, 0x14400126, 0x8f99f314, 0x0320f809, 0x8e040010, 0x8fbc0010, 0x14400035, 0x00408025,)),
    (0x4a3ae0, 'row handler, switch row: Wi-Fi flag, confirm kind 5 msg_bt_open, switchBluetooth(flag, 1), rebuild',
     (0x8f82a948, 0x90440000, 0x1480002f, 0x00409825, 0x8f91a944, 0x92220000, 0x10400021, 0x24050001, 0x8f99f524, 0x27b00018, 0x24060408, 0x00002825, 
      0x0320f809, 0x02002025, 0x24020005, 0x8fbc0010, 0x24060200, 0x27a50020, 0xafa20018, 0x8f84a708, 0x8f99a90c, 0x0320f809, 0x248445a8, 0x02002825, 
      0x8fbc0010, 0x8f84a708, 0x8f99a980, 0x0320f809, 0x24844570, 0x2403000a, 0x1443000d, 0x8fbc0010, 0x92220000, 0x10400004, 0x8f99a994, 0x0320f809, 
      0x24040001, 0x8fbc0010, 0x92640000, 0x24050001, 0x8f99a998, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99add4, 0x27393734, 0x0411fee6,)),
    (0x4a3c04, 'row handler, Search row (btStartSearch) and the device rows: bt_connectstatus guard, btStopSearch',
     (0x16020006, 0x8f82aeec, 0x8f99af18, 0x0320f809, 0x00000000, 0x1000ffed, 0x00000000, 0x8c420000, 0x1440ffea, 0x8f99aec4, 0x0320f809, 0x00000000,)),
    (0x4a3ca8, 'row handler, forget: confirm kind 1 msg_unpairing, handleBluetoothPair, the output restore, toast 4000 msg_unpaired, getSearchResult, save_start_player(1)',
     (0x8f99f524, 0x27b00420, 0x24060408, 0x00002825, 0x0320f809, 0x02002025, 0x24130001, 0x8fbc0010, 0x24060200, 0x27a50428, 0xafb30420, 0x8f84a708, 
      0x8f99a90c, 0x0320f809, 0x24847b3c, 0x02002825, 0x8fbc0010, 0x8f84a708, 0x8f99a980, 0x0320f809, 0x24844570, 0x2403000a, 0x1443ffb3, 0x8fbc0010, 
      0x8f99af20, 0x0320f809, 0x02202025, 0x2443ffff, 0x2c630002, 0x1060ffac, 0x8fbc0010, 0x24030002, 0x14430015, 0x8f99f524, 0x8f90a984, 0x24050002, 
      0x8f99af24, 0x0320f809, 0x8e040000, 0x8e030000, 0x1062000c, 0x8fbc0010, 0x8f99aa84, 0x0320f809, 0xae020000, 0x10530007, 0x8fbc0010, 0x8f99ae64, 
      0x00003025, 0x8e040000, 0x0320f809, 0x24050003, 0x8fbc0010, 0x8f99f524, 0x27b00018, 0x24060408, 0x00002825, 0x0320f809, 0x02002025, 0x24020001, 
      0x8fbc0010, 0x24060200, 0xafa20018, 0x24020fa0, 0x27a50020, 0xafa2001c, 0x8f84a708, 0x8f99a90c, 0x0320f809, 0x24847b4c, 0x02002825, 0x8fbc0010, 
      0x8f84a708, 0x8f99a980, 0x0320f809, 0x248445c4, 0x8fbc0010, 0x8f99a87c, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99aa88, 0x0320f809, 0x24040001, 
      0x1000ff65, 0x8fbc0010,)),
    (0x4a3e20, 'row handler, device tap: handleBluetoothLink and its results (-1 toast, 1 restore + toast + getSearchResult + save_start_player(1))',
     (0x8f99af28, 0x0320f809, 0x02202025, 0x00408025, 0x2402ffff, 0x1602001b, 0x8fbc0010, 0x8f99f524, 0x27b00018, 0x24060408, 0x00002825, 0x0320f809, 
      0x02002025, 0x24020001, 0x8fbc0010, 0x24060200, 0xafa20018, 0x240207d0, 0x27a50020, 0xafa2001c, 0x8f84a708, 0x24847b5c, 0x8f99a90c, 0x0320f809, 
      0x00000000, 0x02002825, 0x8fbc0010, 0x8f84a708, 0x8f99a980, 0x0320f809, 0x248445c4, 0x1000ff4c, 0x00000000, 0x24020001, 0x1602ff3a, 0x8f99add4, 
      0x8f91a984, 0x24050002, 0x8f99af24, 0x0320f809, 0x8e240000, 0x8e230000, 0x1062000c, 0x8fbc0010, 0x8f99aa84, 0x0320f809, 0xae220000, 0x10500007, 
      0x8fbc0010, 0x8f99ae64, 0x00003025, 0x8e240000, 0x0320f809, 0x24050003, 0x8fbc0010, 0x8f99f524, 0x27b00018, 0x24060408, 0x00002825, 0x0320f809, 
      0x02002025, 0x24020001, 0x8fbc0010, 0x24060200, 0xafa20018, 0x240207d0, 0x27a50020, 0xafa2001c, 0x8f84a708, 0x8f99a90c, 0x0320f809, 0x24847b70, 
      0x02002825, 0x8fbc0010, 0x8f84a708, 0x8f99a980, 0x0320f809, 0x248445c4, 0x1000ffa4, 0x8fbc0010,)),
    (0x4a3f60, 'row handler, the init toast (kind 1, 2000 ms, msg_btinit_run)',
     (0x8f99f524, 0x27b00018, 0x24060408, 0x00002825, 0x0320f809, 0x02002025, 0x24020001, 0x8fbc0010, 0x24060200, 0xafa20018, 0x240207d0, 0x27a50020, 
      0xafa2001c, 0x8f84a708, 0x1000ffb7, 0x248445b4,)),
    (0x4a3fa0, 'timer 0x4a3fa0: refresh flag, init spinner, scan count-down, btStopSearch, getSearchResult, bt_start_scan',
     (0x3c1c0056, 0x279cff30, 0x0399e021, 0x27bdffd8, 0x8f82a99c, 0xafbc0010, 0xafb00020, 0xafbf0024, 0x90430000, 0x10600008, 0x8c840024, 0x8f99add4, 
      0xafa40018, 0x27393734, 0x0411fdd6, 0xa0400000, 0x8fbc0010, 0x8fa40018, 0x8f82a948, 0x90420000, 0x10400030, 0x8fb00020, 0x8f82a878, 0x8c430000, 
      0x1860000f, 0x8f83af2c, 0x90620000, 0x7c021420, 0x18400029, 0x24020008, 0x90620000, 0x2442ffff, 0x7c021420, 0xa0620000, 0x90650000, 0x8f99af30, 
      0x0411fb68, 0x7c052c20, 0x1000001d, 0x00000000, 0x8c420000, 0x1440001b, 0x8fb00020, 0x8f82aedc, 0x90430000, 0x7c031c20, 0x18600027, 0x8f90af34, 
      0x90430000, 0x24050001, 0x2463ffff, 0x7c031c20, 0xa0430000, 0x90430000, 0x7c031c20, 0x14650011, 0x8f99aec4, 0x0320f809, 0xafa40018, 0x8fbc0010, 
      0x8f99a87c, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99add4, 0x27393734, 0x0411fda2, 0x8fa40018, 0x8fb00020, 0x24020008, 0x8fbf0024, 0x03e00008, 
      0x27bd0028, 0x90430000, 0x24050019, 0x7c031c20, 0x00a001f4, 0x0065001a, 0x00001810, 0x14600003, 0x00000000, 0x1000ffea, 0xafa40018, 0x90450000, 
      0x1000ffcf, 0x8f99af30, 0x92020000, 0x304200ff, 0x1040ffeb, 0x8f99af18, 0x0320f809, 0x00000000, 0xa2000000, 0x1000ffe7, 0x8fb00020,)),
    (0x4a411c, 'page init 0x4a411c: handlers, the three clears, local name, btStartSearch',
     (0x3c1c0056, 0x279cfdb4, 0x0399e021, 0x10800056, 0x00000000, 0x27bdffe0, 0x8f86add4, 0x2405012e, 0x8f99a830, 0x00803825, 0xafbf001c, 0x24c628bc, 
      0xafbc0010, 0xafb00018, 0x0320f809, 0x00808025, 0x2405012c, 0x8fbc0010, 0x02003825, 0x02002025, 0x8f86add4, 0x8f99a830, 0x0320f809, 0x24c62a20, 
      0x2405012d, 0x8fbc0010, 0x02003825, 0x02002025, 0x8f86add4, 0x8f99a830, 0x0320f809, 0x24c63a28, 0x02003025, 0x8fbc0010, 0x02002025, 0x8f85add4, 
      0x8f99a840, 0x0320f809, 0x24a52a68, 0x8fbc0010, 0x8f82aedc, 0xa0400000, 0x8f82a99c, 0xa0400000, 0x8f82af34, 0xa0400000, 0x8f82a948, 0x90420000, 
      0x1040001c, 0x8f99add4, 0x8f82a878, 0x8c420000, 0x14400019, 0x27393734, 0x8f99f524, 0x24060100, 0x8f84aecc, 0x0320f809, 0x00002825, 0x24060020, 
      0x8fbc0010, 0x8f99f524, 0x8f84af38, 0x0320f809, 0x00002825, 0x8fbc0010, 0x8f99af3c, 0x8f85af38, 0x8f84aecc, 0x0320f809, 0x00000000, 0x8fbc0010, 
      0x8f99af18, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99add4, 0x27393734, 0x0411fd37, 0x02002025, 0x8fbc0010, 0x8f99add4, 0x27392b68, 0x0411fa3f, 
      0x02002025, 0x00001025,)),
    (0x4a28bc, 'window close handler 0x4a28bc: btStopSearch',
     (0x3c1c0056, 0x279c1614, 0x0399e021, 0x27bdffe0, 0x8f99aec4, 0xafbf001c, 0xafbc0010, 0x0320f809, 0x00000000, 0x00001025, 0x8fbf001c, 0x03e00008,)),
    (0x4a29cc, 'return handler 0x4a29cc: btStopSearch, timer removal, window_close',
     (0x3c1c0056, 0x279c1504, 0x0399e021, 0x27bdffd8, 0x8f99aec4, 0xafbf0024, 0xafbc0010, 0xafa40018, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99add4, 
      0x273928f0, 0x0411ffbb, 0x8fa40018, 0x8fbc0010, 0x8fa40018, 0x8fbf0024, 0x8f99a924, 0x03200008, 0x27bd0028,)),
    (0x4a2a20, 'to-background handler 0x4a2a20: timer removal, btStopSearch',
     (0x3c1c0056, 0x279c14b0, 0x0399e021, 0x27bdffe0, 0x8f99add4, 0xafbf001c, 0xafbc0010, 0x273928f0, 0x0411ffab, 0x00000000, 0x8fbc0010, 0x8f99aec4, 
      0x0320f809, 0x00000000, 0x00001025, 0x8fbf001c,)),
    (0x4a4898, 'Quality handler 0x4a4850: guards, reconnect confirm, the five stores, output restore, btcoding, switchBtPriority, config, bluetoothLink(2), refresh flag',
     (0x8f82aeec, 0x8c420000, 0x14400093, 0x8f91aed0, 0x8f99f314, 0x0320f809, 0x8e040010, 0x8e340000, 0x00408025, 0x1282008c, 0x8fbc0010, 0x8f95a9d4, 
      0x8f99f524, 0x92a20000, 0x304200ff, 0x10400091, 0x8f96a9e4, 0x8ec20000, 0x1840008f, 0x27b30420, 0x27b30018, 0x24060408, 0x00002825, 0x0320f809, 
      0x02602025, 0x24140001, 0x8fbc0010, 0x24060200, 0x27a50020, 0xafb40018, 0x8f84a708, 0x8f99a90c, 0x0320f809, 0x24847bc8, 0x02602825, 0x8fbc0010, 
      0x8f84a708, 0x8f99a980, 0x0320f809, 0x24844570, 0x2403000a, 0x1443006c, 0x8fbc0010, 0x8f99aa80, 0x0320f809, 0x00000000, 0x2403ffff, 0x8fbc0010, 
      0x24050002, 0xa2a00000, 0xaec00000, 0x8f82af40, 0x8f93a984, 0x8f99af24, 0xac400000, 0x8f82af44, 0x8e640000, 0xac430000, 0x8f82af48, 0xac400000, 
      0x0320f809, 0x00000000, 0x8e630000, 0x1062000c, 0x8fbc0010, 0x8f99aa84, 0x0320f809, 0xae620000, 0x10540007, 0x8fbc0010, 0x8f99ae64, 0x00003025, 
      0x8e640000, 0x0320f809, 0x24050003, 0x8fbc0010, 0x8f99f524, 0x27b30420, 0x24060040, 0x00002825, 0x0320f809, 0x02602025, 0x24050040, 0x8fbc0010, 
      0x02602025, 0x8e270000, 0x8f94a708, 0x8f99a868, 0x0320f809, 0x268673a8, 0x24060001, 0x8fbc0010, 0x02402025, 0x8f99a860, 0x0320f809, 0x02602825, 
      0x8fbc0010, 0x10400006, 0x00402025, 0x8f858020, 0x8f99a92c, 0x0320f809, 0x24a58710, 0x8fbc0010, 0x8f99f524, 0x24060040, 0x00002825, 0x0320f809, 
      0x02602025, 0x268673a8, 0x8fbc0010, 0x24050040, 0x02003825, 0x8f99a868, 0x0320f809, 0x02602025, 0x24060001, 0x8fbc0010, 0x02402025, 0x8f99a860, 
      0x0320f809, 0x02602825, 0x8fbc0010, 0x10400006, 0x00402025, 0x8f858020, 0x8f99a92c, 0x0320f809, 0x24a58740, 0x8fbc0010, 0x8f99af4c, 0x02002025, 
      0x0320f809, 0xae300000, 0x8fbc0010, 0x8e240000, 0x8f86a708, 0x8f85a708, 0x8f99a934, 0x24c67bd8, 0x0320f809, 0x24a54540, 0x8fbc0010, 0x8f99af50, 
      0x0320f809, 0x24040002, 0x8fbc0010, 0x8f82a99c, 0x24030001, 0xa0430000,)),
    (0x4a4bf0, 'Quality handler, not connected: btcoding, switchBtPriority, config, the refresh flag',
     (0x8f99af4c, 0x02002025, 0x0320f809, 0xae300000, 0x8fbc0010, 0x8e240000, 0x8f86a708, 0x8f85a708, 0x8f99a934, 0x24c67bd8, 0x0320f809, 0x24a54540, 
      0x1000ffb0, 0x8fbc0010,)),
    (0x4d5178, 'switchBluetooth 0x4d516c: the stores, the off path, the on path (bluetoothInit(scan))',
     (0x27bdffd8, 0x8f82a9a4, 0xafbc0010, 0xafb10020, 0xafb0001c, 0xafbf0024, 0xa0400000, 0x8f82af34, 0x8f91a948, 0xa0400000, 0x10800051, 0x24020001, 
      0x8f82a9cc, 0x80430000, 0x24020001, 0x14620006, 0x8f99af88, 0x8f99b04c, 0x0320f809, 0x00000000, 0x8fbc0010, 0x8f99af88, 0x0320f809, 0x00000000, 
      0x24030001, 0x14430013, 0x8fbc0010, 0x8f90a984, 0x24050002, 0x8f99af24, 0x041107ae, 0x8e040000, 0x8e030000, 0x1062000b, 0x8fbc0010, 0x8f99aa80, 
      0x0411343e, 0xae020000, 0x00003025, 0x8fbc0010, 0x24050003, 0x8f99ae64, 0x04110751, 0x8e040000, 0x8fbc0010, 0x8f99aec4, 0x0411f983, 0x00000000, 
      0x8fbc0010, 0x8f99b70c, 0x0411ff98, 0x00000000, 0x8fbc0010, 0x8f99b710, 0x0411fba5, 0x00000000, 0x8fbc0010, 0x8f99b714, 0x0411f6b6, 0x00000000, 
      0x8fbc0010, 0x8f82a98c, 0x8f99a988, 0x041106a0, 0x8c440000, 0x8fbc0010, 0x8f82aee8, 0x8f99f494, 0x0320f809, 0x8c440000, 0x8fbc0010, 0x8f82b6e0, 
      0x8f99f494, 0x0320f809, 0x8c440000, 0x24040001, 0x8fbc0010, 0x8f99aa88, 0x0411344d, 0xa2200000, 0x8fbc0010, 0x8f868020, 0x8f85a708, 0x92240000, 
      0x8f99a934, 0x24c6a2a4, 0x8fb0001c, 0x24a54540, 0x8fb10020, 0x8fbf0024, 0x100005d2, 0x27bd0028, 0x8f99a880, 0x10a00002, 0xa2220000, 0x24040001, 
      0x0411f4e8, 0x00000000, 0x1000ffee, 0x8fbc0010,)),
    (0x4d5308, 'handleBluetoothLink 0x4d5308: entry, the index check',
     (0x3c1c0053, 0x279cebc8, 0x0399e021, 0x0481000a, 0x00001025, 0x03e00008, 0x00000000, 0x00001025, 0x8fb00038, 0x8fb1003c, 0x8fb20040, 0x8fbf0044, 
      0x03e00008, 0x27bd0048, 0x27bdffb8,)),
    (0x4d66e4, 'handleBluetoothPair 0x4d66e4: entry',
     (0x3c1c0053, 0x279cd7ec, 0x0399e021, 0x27bdffb8, 0xafbc0010, 0xafb00038, 0xafb1003c, 0xafb20040, 0x04810009, 0xafbf0044, 0x00008825, 0x02201025, 
      0x8fb00038, 0x8fb1003c, 0x8fb20040, 0x8fbf0044,)),
    (0x4a3434, 'device row 0x4a33c8: the last link item',
     (0x8f99aee0, 0x0320f809, 0x00000000, 0x27a50180, 0x8fbc0018, 0x2444ffff, 0x8f99aee4, 0x0320f809, 0x02c03025,)),
    (0x4a3528, 'device row: the MAC compare, bt_connectstatus == 1',
     (0x8f99f56c, 0x02c02825, 0x0320f809, 0x02a02025, 0x8fbc0018, 0x8f90add4, 0x14400065, 0x26102d2c, 0x8f82aeec, 0x8c430000, 0x24020001, 0x14620045, 
      0x8fa30180,)),
    (0x4a366c, 'device row: link status 3, bt_showcoding 1..4 or 13, checkPairDev',
     (0x24020003, 0x14620019, 0x8f82a9e4, 0x8c430000, 0x2462ffff, 0x2c420004, 0x14400003, 0x2402000d, 0x14620013, 0x8f99aef0, 0x2406000a, 0xafa00010, 
      0x240700c8, 0x02602825, 0x0200c825, 0x0411fda0, 0x02402025, 0x240600c8, 0x8fbc0018, 0x8f85a708, 0x24a57ab0, 0x8f99add4, 0x27392c30, 0x0411fd59, 
      0x02402025, 0x1000ffb7, 0x8fbc0018, 0x8f99aef0, 0x0320f809, 0x02a02025, 0x240700c8, 0x1040000b,)),
    (0x4d28bc, 'adjustA2dpVolume 0x4d28ac: bluetoothflag, bt_linkstatus, bt_showcoding, btrecv_pageflag, the reading',
     (0x8f82a948, 0xafbc0010, 0xafb00018, 0xafbf001c, 0x90420000, 0x10400019, 0x8f82a9d4, 0x90420000, 0x304200ff, 0x10400015, 0x8f82a9e4, 0x8c420000, 
      0x18400012, 0x8f82a960, 0x8c420000, 0x1440000f, 0x8f99f43c, 0x0320f809, 0x00808025, 0x00402025, 0x2c420080, 0x10400009, 0x8fbc0010, 0x1600000c,)),
    (0x4da168, 'get_bluetoothcoding_text 0x4da15c: i < 8, the table copy, the key copy, 1 / -1',
     (0x28830008, 0x1060001b, 0x00000000, 0x27bdffb8, 0x8f99f848, 0x24060020, 0xafb10040, 0x00a08825, 0xafb0003c, 0x00808025, 0xafbf0044, 0x27a40018, 
      0xafbc0010, 0x00108080, 0x8f85a888, 0x0320f809, 0x24a5ca08, 0x8fbc0010, 0x00502021, 0x8c850000, 0x8f99f324, 0x0320f809, 0x02202025, 0x24020001, 
      0x8fb0003c, 0x8fb10040, 0x8fbf0044, 0x03e00008, 0x27bd0048, 0x03e00008, 0x2402ffff,)),
    (0x4d4980, 'getBtLinkItem 0x4d4938: an index out of range leaves the outputs alone',
     (0x06000019, 0x8fbc0010, 0x8f91b6e8, 0x8f99f31c, 0x0320f809, 0x8e240000, 0x0202102b, 0x10400012,)),
    (0x4e5bf8, 'config_init: BTCODING atoi, >= 8 -> 0',
     (0x8f99f314, 0x0320f809, 0x02002025, 0x24060100, 0x8fbc0018, 0x2c430008, 0x0003100a, 0x00002825, 0x02002025, 0x8f83aed0, 0x8f99f524, 0x0320f809, 
      0xac620000,)),
)
BLUETOOTH_PINS = tuple((a + 4 * i, w, what) for a, what, ws in BLUETOOTH_RUNS for i, w in enumerate(ws)) + tuple((0x97ca08 + 4 * i, p, f'codec table: the key of codec {i}') for i, p in enumerate((0x74a590, 0x74a5a0, 0x74a5b0, 0x74a5c0, 0x74a5d0, 0x74a5dc, 0x74a5e8, 0x74a5f8)))

# libhardware2's GPIO wrapper that stock's toolsGpioGetValue (0x5e5cac) calls and patch/power.c repeats: gpio_open (open("/dev/gpio", O_RDWR)) and gpio_get_value (ioctl(fd, 0x2000477a, name)); the text is mapped at its file offsets
GPIO_LIB = 'usr/lib/libhardware2.so'
GPIO_OPEN, GPIO_GET = 0x556c, 0x57bc
GPIO_LIB_WORDS = ((0x5580, 0x24050002, 'gpio_open: addiu a1, zero, 2 (O_RDWR)'), (0x57d4, 0x3c052000, 'gpio_get_value: lui a1, 0x2000'), (0x57e8, 0x24a5477a, 'gpio_get_value: addiu a1, a1, 0x477a (delay slot)'))
GPIO_NAME_ADDR = 0x74a8ec   # demo: the "PD17" string usb_detect passes (BATTERY_PINS)

# The saved play type of spoken audio (patch/pcmodel.c pc_mem_type, payload hook 42): save_memoryplay_info's `jalr mclGetPlayType` (after mclGetPlayStatus and mclGetPlayPos) becomes `jal pc_mem_type`. The
# result is moved to s2 at once (0x4e338c) and stored to the Memory Playback record's first word at 0x4e3440 (sw s2, (a0)); the delay slot (move s0, v0) keeps the position.
MEMTYPE_SITE = 0x4e3384
MEMTYPE_PINS = (   # (address, stock word, what it proves)
    (0x4e3340, 0x3c1c0052, 'save_memoryplay_info prologue (1/3)'), (0x4e3344, 0x279c0b90, 'save_memoryplay_info prologue (2/3)'), (0x4e3348, 0x0399e021, 'save_memoryplay_info prologue (3/3)'),
    (0x4e3380, 0x8f99aa98, 'save_memoryplay_info: lw t9, GOT mclGetPlayType'), (MEMTYPE_SITE, 0x0320f809, 'save_memoryplay_info: jalr mclGetPlayType (the hook replaces it)'),
    (MEMTYPE_SITE + 4, 0x00408025, 'its delay slot: move s0, v0 (the position)'), (MEMTYPE_SITE + 8, 0x00409025, 'save_memoryplay_info: move s2, v0 (the type)'),
    (0x4e3430, 0x8f84b7cc, 'save_memoryplay_info: lw a0, GOT g_memory_info'), (0x4e3440, 0xac920000, 'save_memoryplay_info: sw s2, (a0): the type into the record'),
)

# The Volume page (patch/volume.c, docs/modules/volume.md, payload hook 33): the status bar tap's `bal navigator_to_with_context("dialog/volume_dialog", 2)` in on_wm_tsup_fun (0x4cd8dc; a0 comes in the delay slot,
# a1 = 2 before it, `lw gp` after) becomes `jal vol_tap_open`. The page runs stock's own dialog code on its window: the refresh 0x47d664 (volume_showpage 0x97c790: 1 is the strip, otherwise the page: vol_label "VOL: n"
# and the slider from volume, or btsource_volume while headset_output is 2), the - / + / slider / key handlers, and the stop 0x47d9f8 of the 3 s auto-close timer the handlers' reset 0x47de2c adds (the id in the
# window property "timer_idex"); each entry, the dialog init's and the visitor's bindings and the timer words are pinned.
VOLUME_SITE = 0x4cd964
VOLUME_PINS = (   # (address, stock word, what it proves)
    (0x4cd8dc, 0x3c1c0053, 'on_wm_tsup_fun prologue (1/3)'), (0x4cd8e0, 0x279c65f4, 'on_wm_tsup_fun prologue (2/3)'), (0x4cd8e4, 0x0399e021, 'on_wm_tsup_fun prologue (3/3)'),
    (0x4cd920, 0x8ca20018, 'on_wm_tsup_fun: the event x'), (0x4cd924, 0x2442ffb0, 'on_wm_tsup_fun: x - 80'), (0x4cd928, 0x2c4200bf, 'on_wm_tsup_fun: x in 80 .. 269'),
    (0x4cd934, 0x8ca2001c, 'on_wm_tsup_fun: the event y'), (0x4cd938, 0x2842002a, 'on_wm_tsup_fun: y < 42'), (0x4cd94c, 0x2842002a, 'on_wm_tsup_fun: pressdown_y < 42'),
    (0x4cd958, 0x8f848020, 'on_wm_tsup_fun: lw a0, GOT page 0x750000'), (0x4cd95c, 0x24050002, 'on_wm_tsup_fun: a1 = 2 (the full page)'), (0x4cd960, 0x8f99a980, 'on_wm_tsup_fun: lw t9, GOT navigator_to_with_context'),
    (VOLUME_SITE, 0x041110f8, 'on_wm_tsup_fun: bal navigator_to_with_context (the hook replaces it)'), (VOLUME_SITE + 4, 0x24849a94, 'its delay slot: a0 = "dialog/volume_dialog"'),
    (VOLUME_SITE + 8, 0x8fbc0010, 'on_wm_tsup_fun: lw gp after the call'),
    (0x534fa0, 0x24050103, 'home_page_init: widget_on(wm, 0x103 POINTER_UP, ...) (1/2)'), (0x534fa8, 0x8f86c1d8, 'home_page_init: ... handler on_wm_tsup_fun (2/2)'),
    (0x4d1d48, 0x3c1c0053, 'navigator_to_with_context prologue (1/3)'), (0x4d1d4c, 0x279c2188, 'navigator_to_with_context prologue (2/3)'), (0x4d1d50, 0x0399e021, 'navigator_to_with_context prologue (3/3)'),
    (0x47d664, 0x3c1c0058, 'volume refresh prologue (1/3)'), (0x47d668, 0x279c686c, 'volume refresh prologue (2/3)'), (0x47d66c, 0x0399e021, 'volume refresh prologue (3/3)'),
    (0x47d9f8, 0x3c1c0058, 'volume timer stop prologue (1/3)'), (0x47d9fc, 0x279c64d8, 'volume timer stop prologue (2/3)'), (0x47da00, 0x0399e021, 'volume timer stop prologue (3/3)'),
    (0x47de2c, 0x3c1c0058, 'volume timer reset prologue (1/3)'), (0x47de30, 0x279c60a4, 'volume timer reset prologue (2/3)'), (0x47de34, 0x0399e021, 'volume timer reset prologue (3/3)'),
    (0x47dea8, 0x24050bb8, 'volume timer reset: timer_modify(id, 3000)'),
    (0x47dc88, 0x3c1c0058, 'volume timer add prologue (1/3)'), (0x47dc8c, 0x279c6248, 'volume timer add prologue (2/3)'), (0x47dc90, 0x0399e021, 'volume timer add prologue (3/3)'),
    (0x47dce8, 0x24060bb8, 'volume timer add: widget_add_timer(win, 0x47d630, 3000)'), (0x47dcdc, 0x24060064, 'volume timer add: the 100 ms variant'),
    (0x47d630, 0x3c1c0058, 'volume timer callback prologue'), (0x47d650, 0x8c840024, 'volume timer callback: window_close(*(timer + 0x24))'),
    (0x47e034, 0x3c1c0058, 'volume + handler prologue (1/3)'), (0x47e038, 0x279c5e9c, 'volume + handler prologue (2/3)'), (0x47e03c, 0x0399e021, 'volume + handler prologue (3/3)'),
    (0x47e180, 0x3c1c0058, 'volume - handler prologue (1/3)'), (0x47e184, 0x279c5d50, 'volume - handler prologue (2/3)'), (0x47e188, 0x0399e021, 'volume - handler prologue (3/3)'),
    (0x47e1b8, 0x3c1c0058, 'volume slider handler prologue (1/3)'), (0x47e1bc, 0x279c5d18, 'volume slider handler prologue (2/3)'), (0x47e1c0, 0x0399e021, 'volume slider handler prologue (3/3)'),
    (0x47e330, 0x3c1c0058, 'volume key handler prologue (1/3)'), (0x47e334, 0x279c5ba0, 'volume key handler prologue (2/3)'), (0x47e338, 0x0399e021, 'volume key handler prologue (3/3)'),
    (0x47dbc8, 0x2405010c, 'the dialog visitor: EVT_CLICK for the buttons'), (0x47dc1c, 0x24c6e034, 'the dialog visitor: btn_add -> 0x47e034'), (0x47dc48, 0x24c6e180, 'the dialog visitor: btn_dec -> 0x47e180'),
    (0x47dc74, 0x2405011d, 'the dialog visitor: vol_slider EVT_VALUE_CHANGING'), (0x47dc7c, 0x24c6e1b8, 'the dialog visitor: vol_slider -> 0x47e1b8'),
)
# Swap Prev / Next (patch/keyspower.c kp_key_map, docs/modules/keyspower.md "Swap Prev / Next", payload hook 35): the /dev/input/event1 thread (0x637870, started by input_thread_run; the previous, play and next
# buttons) maps a key event's Linux code through the table 0x75b324 (`v0 = table[code & 0xff]`) and stores the result in the event at 0x58(sp). The load and the store become `j pod_keys_site; nop`: the stub
# loads the word, calls kp_key_map, stores its answer at 0x58(sp) and resumes at 0x637bd0 (also the target of the branch at 0x637aa8, so a jump there is a normal path). Nothing reads $v0, $v1 or $a0 .. $a3
# set before the site after it ($a0 is stored at 0x637bbc and reloaded at 0x637bd0; $a1, $a2, $t9 are set again before the dispatch call), $ra is saved by the prologue and reloaded by the epilogue, and
# $gp is set again. The table's two entries and the event2 table's (0x75b7f8, the volume keys' thread, gives them 0xeb / 0xea) are pinned: only event1 sends the previous and next codes. Reached on every key event at boot.
KEYS_SITE, KEYS_RESUME = 0x637bc8, 0x637bd0
KEYS_PINS = (   # (address, stock word, what it proves)
    (0x637870, 0x3c1c003d, 'event1 thread prologue (1/3)'), (0x637874, 0x279cc660, 'event1 thread prologue (2/3)'), (0x637878, 0x0399e021, 'event1 thread prologue (3/3)'),
    (0x63787c, 0x27bdff68, 'event1 thread: addiu sp, sp, -0x98'), (0x6378a4, 0xafbf0094, 'event1 thread: sw ra, 0x94(sp)'),
    (0x637b84, 0x8fa3007c, 'event1 thread: lw v1, 0x7c(sp), the event value (the stub reads it again)'), (0x637b90, 0x2405010f, 'event1 thread: 0x10f KEY_DOWN for a non-zero value'),
    (0x637ba8, 0x24040113, 'event1 thread: 0x113 KEY_UP for value 0'), (0x637bb0, 0x00a3200b, 'event1 thread: movn a0, a1, v1 (down unless the value is 0)'),
    (0x637bac, 0x304200ff, 'event1 thread: code & 0xff'), (0x637bb4, 0x00021080, 'event1 thread: index * 4'), (0x637bb8, 0x8f838054, 'event1 thread: lw v1, GOT page 0x760000'),
    (0x637bbc, 0xafa40040, 'event1 thread: the event type stored before the site'), (0x637bc0, 0x2463b324, 'event1 thread: v1 = the key table 0x75b324'), (0x637bc4, 0x00431021, 'event1 thread: v0 = &table[code]'),
    (KEYS_SITE, 0x8c420000, 'event1 thread: lw v0, (v0) (the hook replaces it)'), (KEYS_SITE + 4, 0xafa20058, 'event1 thread: sw v0, 0x58(sp), the key in the event (the stub does it)'),
    (KEYS_RESUME, 0x8fa4002c, 'event1 thread: lw a0, 0x2c(sp) (the resume point)'), (0x637aa8, 0x10000049, 'event1 thread: b 0x637bd0 (the resume point is a branch target)'),
    (0x637c20, 0x8fbf0094, 'event1 thread: lw ra, 0x94(sp) in the epilogue'),
    (0x637df8, 0x0320f809, 'input_thread_run: tk_thread_create (1/2)'), (0x637dfc, 0x24847870, 'input_thread_run: ... with the thread 0x637870 (2/2)'),
    (0x75b324 + 0xa3 * 4, 0xd7, 'event1 table: KEY_NEXTSONG -> next'), (0x75b324 + 0xa5 * 4, 0xd6, 'event1 table: KEY_PREVIOUSSONG -> previous'),
    (0x75b7f8 + 0xa3 * 4, 0xeb, 'event2 table: KEY_NEXTSONG is not next there'), (0x75b7f8 + 0xa5 * 4, 0xea, 'event2 table: KEY_PREVIOUSSONG is not previous there'),
)
# Crossfade (patch/xfadeset.c, docs/modules/crossfade.md): early gapless preload via Hook 36 (rd_auto_change -> xfade_auto_change).
# Calls stock mclGetPlayTime and mcl_gapless_preload (both pinned prologues); no new binary hook in demo.
XFADE_PINS = (   # (address, stock word, what it proves)
    (0x5d35a8, 0x3c1c0043, 'mclGetPlayTime prologue (1/3)'),
    (0x5d35ac, 0x279c0928, 'mclGetPlayTime prologue (2/3)'),
    (0x5d35b0, 0x0399e021, 'mclGetPlayTime prologue (3/3)'),
    (0x5d35e0, 0x2644ab20, 'mclGetPlayTime: mutex at 0xa0ab20 (MCL_TIME_MUTEX)'),
    (0x5d35f4, 0x2442ab50, 'mclGetPlayTime: playinfo struct at 0xa0ab50 (MCL_PLAYINFO)'),
    (0x5d35f8, 0x8c43000c, 'mclGetPlayTime: cur_s at MCL_PLAYINFO + 0xc'),
    (0x5d3600, 0x8c420008, 'mclGetPlayTime: total_s at MCL_PLAYINFO + 8'),
    (0x5d6450, 0x8fa20018, 'mclAutoChange post-handoff preload: lw total_s from stack'),
    (0x5d6454, 0x28430003, 'mclAutoChange post-handoff preload: slti total_s < 3 skips preload'),
    (0x5d6484, 0x0411ea87, 'mclAutoChange post-handoff preload: bal mcl_gapless_preload'),
    (0x5d0ea4, 0x3c1c0043, 'mcl_gapless_preload prologue (1/3)'),
    (0x5d0ea8, 0x279c302c, 'mcl_gapless_preload prologue (2/3)'),
    (0x5d0eac, 0x0399e021, 'mcl_gapless_preload prologue (3/3)'),
    (0x5d0eb0, 0x27bdffd8, 'mcl_gapless_preload frame setup'),
    (0x5d0eb4, 0xafb10020, 'mcl_gapless_preload save s1'),
)
