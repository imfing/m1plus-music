/* M1+ Music Settings > Buttons & Power (docs/modules/keyspower.md): the state behind our page's four controls and their two pickers.
 *
 * Every state is stock's own, loaded by config_init (anything out of range becomes its default) and shown by stock's pages, which stay reachable through All System Settings and read the same words:
 * systemset/keylock_page (the byte keylock_flag, the word keylock_mode), the row 7 of systemset/sysset_page (the byte doublewake_flag) and systemset/powermanager_page (the byte standbyflag, the word
 * savepowermode). Nothing of ours is saved. The setters repeat what stock's click handlers do, in their order (tools/pod.py KEYSPOWER_PINS), and nothing else: stock's handlers need their own widgets for
 * the refresh, so they are not called. */
#include "offsets.inc"
#include "stock.h"
#include "home.h"
#include "entries.h"

#define KP_SHUTDOWN_MAX 4 /* stock's last duration (10 minutes) */

#define lock_flag (*(volatile unsigned char *)KEY_LOCK_FLAG)
#define lock_mode (*(volatile int *)KEY_LOCK_MODE)
#define tap_wake (*(volatile unsigned char *)TAP_WAKE)
#define standby_flag (*(volatile unsigned char *)STANDBY_FLAG)
#define shutdown_mode (*(volatile int *)SHUTDOWN_MODE)

/* Button Lock: 0 off, else the mode, 1 the volume keys, 2 the other keys, 3 both (the gates read the byte and the word on every key, so a change is live at once). */
int kp_lock(void) {
    int m = lock_mode;
    if (!(lock_flag & 1)) return 0;
    return m >= 1 && m <= 3 ? m : 1;
}

/* Choose it as stock's page does, a click at a time: Off is the switch (the byte xor 1 stored, then the save of LOCKFLAG); a mode is the switch when the lock is off (the byte on, the save), then the choice
 * (nothing when it is the mode already; else the word stored, then the save of LOCKMODE). Off keeps the mode, as stock's page does. 0, or -1 for a choice stock does not have. */
int kp_lock_set(int v) {
    if (v < 0 || v > 3) return -1;
    if (v == 0) {
        if (!(lock_flag & 1)) return 0;
        lock_flag = 0;
        write_int_config(0, "SYSSET", "LOCKFLAG");
        return 0;
    }
    if (!(lock_flag & 1)) {
        lock_flag = 1;
        write_int_config(1, "SYSSET", "LOCKFLAG");
    }
    if (lock_mode != v) {
        lock_mode = v;
        write_int_config(v, "SYSSET", "LOCKMODE");
    }
    return 0;
}

/* Tap to Wake: stock's byte. Its handler (the sysset list's case 7, 0x4ad930) stores the byte xor 1 in the delay slot of the save and does nothing else: the screen's driver is told at the next screen off.
 * The new state. */
int kp_tap(void) { return (tap_wake & 1) != 0; }

int kp_tap_toggle(void) {
    int next = (tap_wake & 1) ^ 1;
    tap_wake = (unsigned char)next;
    write_int_config(next, "SYSSET", "DOUBLEWAKE");
    return next;
}

/* Car Mode: stock's byte car_mode (the sysset list's row 6, case 0x4ad84c; config_init keeps 0 or 1) and the word carmode_startflag. The handler stores the byte xor 1 in the delay slot of the save (the byte first),
 * then sets the row's switch image, then clears carmode_startflag (the idle code's car-power state, on both paths). The byte is read by the standby and shutdown countdown (to_poweroptions), check_usb_status,
 * check_otg_status, home_page_init and the memory-play code, each time they run, so a change is live at once (docs/modules/keyspower.md). The new state. */
#define car_mode (*(volatile unsigned char *)CAR_MODE)
#define car_startflag (*(volatile int *)CAR_STARTFLAG)
int kp_car(void) { return car_mode != 0; }

int kp_car_toggle(void) {
    int next = car_mode ^ 1;
    car_mode = (unsigned char)next;
    write_int_config(next, "SYSSET", "CARMODE");
    car_startflag = 0;
    return next != 0;
}

/* Auto-Standby: stock's byte; Auto-Shutdown and Auto-Standby are never both on. */
int kp_standby(void) { return (standby_flag & 1) != 0; }

/* Stock's switch (0x4a97c4): on from off stores the byte, and when Auto-Shutdown is on clears that word and saves SAVEPOWERMODE; then the save of STANDBYMODE; off stores 0 and saves; both end with
 * reset_poweroptions_timer(1, 1, 0). The new state. */
int kp_standby_toggle(void) {
    if (standby_flag & 1) {
        standby_flag = 0;
        write_int_config(0, "SYSSET", "STANDBYMODE");
    } else {
        standby_flag = 1;
        if (shutdown_mode > 0) {
            shutdown_mode = 0;
            write_int_config(0, "SYSSET", "SAVEPOWERMODE");
        }
        write_int_config(1, "SYSSET", "STANDBYMODE");
    }
    reset_poweroptions_timer(1, 1, 0);
    return standby_flag & 1;
}

/* Auto-Shutdown: stock's word, 0 off, 1 .. 4 = 1, 3, 5, 10 minutes. */
int kp_shutdown(void) {
    int v = shutdown_mode;
    return v >= 0 && v <= KP_SHUTDOWN_MAX ? v : 0;
}

/* Choose it as stock's page does, a click at a time. Off is the switch while it is on (the word 0, the save, reset_poweroptions_timer(1, 1, 0)). A duration from Off is the switch (the word 1 stored, Auto-Standby
 * cleared and saved when it is on, the save of SAVEPOWERMODE, reset_poweroptions_timer(1, 1, 0)), then the choice when it is not 1min; from another duration it is the choice alone (nothing when it is the word already;
 * else the word stored, then the save, then reset_poweroptions_timer(0, 1, 0)). 0, or -1 for a choice stock does not have. */
int kp_shutdown_set(int v) {
    if (v < 0 || v > KP_SHUTDOWN_MAX) return -1;
    if (v == 0) {
        if (shutdown_mode <= 0) return 0;
        shutdown_mode = 0;
        write_int_config(0, "SYSSET", "SAVEPOWERMODE");
        reset_poweroptions_timer(1, 1, 0);
        return 0;
    }
    if (shutdown_mode <= 0) {
        shutdown_mode = 1;
        if (standby_flag & 1) {
            standby_flag = 0;
            write_int_config(0, "SYSSET", "STANDBYMODE");
        }
        write_int_config(1, "SYSSET", "SAVEPOWERMODE");
        reset_poweroptions_timer(1, 1, 0);
    }
    if (shutdown_mode != v) {
        shutdown_mode = v;
        write_int_config(v, "SYSSET", "SAVEPOWERMODE");
        reset_poweroptions_timer(0, 1, 0);
    }
    return 0;
}

/* Swap Prev / Next (SWAPKEYS_FILE, ours): the physical previous and next buttons trade places. The input thread of /dev/input/event1 maps each Linux key code through stock's table 0x75b324; the
 * pod_keys_site stub (tools/pod.py KEYS_SITE) hands the mapped code and the event's value (1 down, 2 repeat, 0 up) to kp_key_map before the code is stored in the event, so every later reader
 * (on_wm_keyup_fun with its own Screen Rotation swap, long press, the Button Lock gates, Cover Flow) sees the swapped key. Bluetooth controls are posted by on_wm_idle_status and stay as they are.
 *
 * kp_swap_state is the saved setting, 0 not read yet, 1 off, 2 on, shared by both threads through atomic loads and stores. The UI thread's toggle stores it after the save; the input thread publishes
 * its first read only while it is still 0 (a compare-and-swap), so a stale read never overwrites a toggle. kp_map is the mapping in use (0 none, 1 stock, 2 swapped) and kp_held the buttons down (bit 0
 * previous, bit 1 next, by physical button), both touched only by the input thread. The mapping is chosen at a key down while no other of the two buttons is down and kept until both are up: a toggle or
 * the kill switch mid-press can neither split one press into a previous down and a next up nor send both buttons as the same key (stock keeps one slot and one long-press timer per key). A lost key up
 * keeps the old mapping until that button's next key up arrives, so stock releases the code it holds. kp_key_map calls no stock function: one file read on the first press, the kill switch's two stats on each choice while the setting is on. */
static int kp_swap_state __attribute__((section(".scratch")));
static unsigned char kp_map __attribute__((section(".scratch")));
static unsigned char kp_held __attribute__((section(".scratch")));

int kp_swap(void) {
    int s = __atomic_load_n(&kp_swap_state, __ATOMIC_ACQUIRE);
    if (!s) {
        int v = set_read(SWAPKEYS_FILE, '0') == '1' ? 2 : 1;
        s = 0;
        if (!__atomic_compare_exchange_n(&kp_swap_state, &s, v, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) v = s;
        s = v;
    }
    return s == 2;
}

int kp_swap_toggle(void) {
    int v = home_set_digit(SWAPKEYS_FILE, !kp_swap(), 1);
    if (v >= 0) __atomic_store_n(&kp_swap_state, v ? 2 : 1, __ATOMIC_RELEASE);
    return v;
}

int kp_key_map(int key, int value) {
    if (key != KEY_PREV && key != KEY_NEXT) return key;
    int bit = key == KEY_NEXT ? 2 : 1;
    if (!kp_map || (value == 1 && !kp_held)) kp_map = kp_swap() && !home_off() ? 2 : 1;
    kp_held = (unsigned char)(value ? kp_held | bit : kp_held & ~bit);
    return kp_map == 2 ? key ^ (KEY_PREV ^ KEY_NEXT) : key;
}
