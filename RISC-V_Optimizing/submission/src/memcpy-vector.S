/* RISC-V RVV based memcpy optimized for mixed random sizes.  */

#include <sysdep.h>
#include <sys/asm.h>

#ifndef MEMCPY
# define MEMCPY memcpy
#endif

#define dst     a0
#define src     a1
#define num     a2

#define ivl     a3
#define dst_ptr a4
#define src_ptr a5

#define tmp     t0
#define vlmax   t1
#define chunk   t2

#define ELEM_LMUL_SETTING m8
#define vdata0  v0
#define vdata1  v8
#define vdata2  v16
#define vdata3  v24

/* Random-size benchmark sweet spot: avoid RVV startup through 128 bytes.  */
#define SCALAR_THRESH 128

    .attribute unaligned_access, 1

ENTRY (__memcpy_vector)
    .option push
    .option arch, +v

    beqz num, L(return)

    li   tmp, SCALAR_THRESH
    bgeu tmp, num, L(scalar_small)

    vsetvli vlmax, zero, e8, ELEM_LMUL_SETTING, ta, ma
    slli chunk, vlmax, 2
    bltu num, chunk, L(vector_simple_entry)

    mv   src_ptr, src
    mv   dst_ptr, dst
L(vector_bulk_loop):
    vle8.v vdata0, (src_ptr)
    add    src_ptr, src_ptr, vlmax
    vle8.v vdata1, (src_ptr)
    add    src_ptr, src_ptr, vlmax
    vle8.v vdata2, (src_ptr)
    add    src_ptr, src_ptr, vlmax
    vle8.v vdata3, (src_ptr)
    add    src_ptr, src_ptr, vlmax

    vse8.v vdata0, (dst_ptr)
    add    dst_ptr, dst_ptr, vlmax
    vse8.v vdata1, (dst_ptr)
    add    dst_ptr, dst_ptr, vlmax
    vse8.v vdata2, (dst_ptr)
    add    dst_ptr, dst_ptr, vlmax
    vse8.v vdata3, (dst_ptr)
    add    dst_ptr, dst_ptr, vlmax

    sub    num, num, chunk
    bgeu   num, chunk, L(vector_bulk_loop)
    beqz   num, L(return)
    j      L(vector_simple_loop)

L(vector_simple_entry):
    mv   src_ptr, src
    mv   dst_ptr, dst
L(vector_simple_loop):
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma
    vle8.v  vdata0, (src_ptr)
    sub     num, num, ivl
    add     src_ptr, src_ptr, ivl
    vse8.v  vdata0, (dst_ptr)
    add     dst_ptr, dst_ptr, ivl
    bnez    num, L(vector_simple_loop)
    ret

L(scalar_small):
    li   tmp, 1
    beq  num, tmp, L(copy_1)
    li   tmp, 4
    bltu num, tmp, L(copy_2_3)
    li   tmp, 8
    bltu num, tmp, L(copy_4_7)
    li   tmp, 16
    bltu num, tmp, L(copy_8_15)
    li   tmp, 32
    bltu num, tmp, L(copy_16_31)
    li   tmp, 65
    bltu num, tmp, L(copy_32_64)
    j    L(copy_65_128)

L(copy_65_128):
    /* 8-byte scalar loop avoids duplicate first/last traffic near 65 bytes.  */
    add  chunk, src, num
    add  vlmax, dst, num
    mv   src_ptr, src
    mv   dst_ptr, dst
    li   ivl, 8
L(copy_8_loop):
    ld   tmp, 0(src_ptr)
    sd   tmp, 0(dst_ptr)
    addi src_ptr, src_ptr, 8
    addi dst_ptr, dst_ptr, 8
    addi num, num, -8
    bgeu num, ivl, L(copy_8_loop)
    beqz num, L(return)
    ld   tmp, -8(chunk)
    sd   tmp, -8(vlmax)
    ret

L(copy_32_64):
    add  src_ptr, src, num
    add  dst_ptr, dst, num
    ld   tmp, 0(src)
    sd   tmp, 0(dst)
    ld   tmp, 8(src)
    sd   tmp, 8(dst)
    ld   tmp, 16(src)
    sd   tmp, 16(dst)
    ld   tmp, 24(src)
    sd   tmp, 24(dst)
    ld   tmp, -32(src_ptr)
    sd   tmp, -32(dst_ptr)
    ld   tmp, -24(src_ptr)
    sd   tmp, -24(dst_ptr)
    ld   tmp, -16(src_ptr)
    sd   tmp, -16(dst_ptr)
    ld   tmp, -8(src_ptr)
    sd   tmp, -8(dst_ptr)
    ret

L(copy_16_31):
    add  src_ptr, src, num
    add  dst_ptr, dst, num
    ld   tmp, 0(src)
    sd   tmp, 0(dst)
    ld   tmp, 8(src)
    sd   tmp, 8(dst)
    ld   tmp, -16(src_ptr)
    sd   tmp, -16(dst_ptr)
    ld   tmp, -8(src_ptr)
    sd   tmp, -8(dst_ptr)
    ret

L(copy_8_15):
    add  src_ptr, src, num
    add  dst_ptr, dst, num
    ld   tmp, 0(src)
    sd   tmp, 0(dst)
    ld   tmp, -8(src_ptr)
    sd   tmp, -8(dst_ptr)
    ret

L(copy_4_7):
    add  src_ptr, src, num
    add  dst_ptr, dst, num
    lw   tmp, 0(src)
    sw   tmp, 0(dst)
    lw   tmp, -4(src_ptr)
    sw   tmp, -4(dst_ptr)
    ret

L(copy_2_3):
    add  src_ptr, src, num
    add  dst_ptr, dst, num
    lhu  tmp, 0(src)
    sh   tmp, 0(dst)
    lhu  tmp, -2(src_ptr)
    sh   tmp, -2(dst_ptr)
    ret

L(copy_1):
    lbu  tmp, 0(src)
    sb   tmp, 0(dst)

L(return):
    ret

    .option pop
END (__memcpy_vector)
libc_hidden_builtin_def (memcpy)
