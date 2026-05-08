/* RISC-V RVV based memmove.
   Copyright (C) 2026 Free Software Foundation, Inc.
   This file is part of the GNU C Library.

   The GNU C Library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2.1 of the License, or (at your option) any later version.

   The GNU C Library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with the GNU C Library; if not, see
   <https://www.gnu.org/licenses/>.  */

#include <sysdep.h>
#include <sys/asm.h>

#ifndef MEMMOVE
# define MEMMOVE memmove
#endif

#define dst a0
#define src a1
#define num a2

#define ivl a3
#define dst_ptr a4
#define src_backward_ptr a5
#define dst_backward_ptr a6

#define ELEM_LMUL_SETTING m8
#define vdata v0

ENTRY (__memmove_vector)
.option push
.option arch, +v
    mv dst_ptr, dst

    /* If src is equal or after dst, all data in src will be loaded before
    overwrited for the overlapping case. We could use faster `forward-copy`. */
    bgeu src, dst, L(forward_copy_loop)
    add src_backward_ptr, src, num
    add dst_backward_ptr, dst, num
    /* If dst inside source data range, we need to use `backward_copy_loop` to
    handle the overlapping issue. */
    bltu dst, src_backward_ptr, L(backward_copy_loop)
L(forward_copy_loop):
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma

    vle8.v vdata, (src)
    sub num, num, ivl
    add src, src, ivl
    vse8.v vdata, (dst_ptr)
    add dst_ptr, dst_ptr, ivl

    bnez num, L(forward_copy_loop)
    ret
L(backward_copy_loop):
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma

    sub src_backward_ptr, src_backward_ptr, ivl
    vle8.v vdata, (src_backward_ptr)
    sub num, num, ivl
    sub dst_backward_ptr, dst_backward_ptr, ivl
    vse8.v vdata, (dst_backward_ptr)
    bnez num, L(backward_copy_loop)
    ret
.option pop
END (__memmove_vector)
libc_hidden_builtin_def (memmove)
