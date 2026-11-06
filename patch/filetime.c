/* M1+ Music song dates: a song's time_create is the card's creation stamp (docs/modules/songs.md "Recently Added dates").
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE). After q2-pod's ringnav_file_created / ringnav_statx (commit 0d00826).
 *
 * Stock's toolsGetFileCreateTime (0x5e4ac8; the library scan's date for every song, stored as songtable.time_create, the order of Recently Added) returns
 * st_ctime from stat(), the directory entry's creation time on FAT, but st_atime when the format byte at 0xa0ac7c says exFAT or NTFS (1 or 2), where stat has no
 * creation time. Every read moves the access time, and a full Update Local Music reads every file, so the whole library was dated to its own day.
 * ft_created replaces the prologue (`j ft_created`): statx(AT_FDCWD, path, 0, STATX_BTIME) reports the stamp exFAT keeps, which reads never move. A failed call, a
 * filesystem that reports no stamp, a zero stamp, a null path or the kill switch /mnt/mmc/m1plus-off runs stock's function through the trampoline.
 * demo imports no statx, so the o32 syscall (4366) is made directly. Cost per call: one access (the kill switch) and one syscall; no allocation, no file I/O of our own.
 */
#include "offsets.inc"
#include "stock.h"
#include "home.h"

extern int stock_file_created_trampoline(const char *path);
extern int ft_statx(int dirfd, const char *path, int flags, unsigned mask, void *buf);

__asm__(".text\n.globl ft_statx\nft_statx:\nli $v0, 4366\nsyscall\njr $ra\nnop\n");

#define AT_FDCWD (-100)
#define STATX_BTIME 0x800u

int ft_created(const char *path) {
    unsigned sx[64]; /* struct statx (256 bytes): stx_mask first, stx_btime.tv_sec at byte 80 */
    if (path && access(KILL_SD, F_OK) != 0 && ft_statx(AT_FDCWD, path, 0, STATX_BTIME, sx) == 0 &&
        (sx[0] & STATX_BTIME) && sx[20])
        return (int)sx[20];
    return stock_file_created_trampoline(path);
}
