/* RISC-V RVV and Zicboz based memset.  */

#include <sysdep.h>
#include <sys/asm.h>

#ifndef MEMSET
# define MEMSET memset
#endif

#define dst     a0
#define value   a1
#define num     a2

#define ivl     a3
#define dst_ptr a5

#define tmp     t0
#define vlmax   t1
#define chunk   t2
#define count   t3

#define ELEM_LMUL_SETTING m8
#define vdata0  v0
#define vdata1  v8
#define vdata2  v16
#define vdata3  v24

/* Tune for random and zero benchmarks in the contest harness.  */
#define SCALAR_THRESH 128
/* The target platform uses 64-byte Zicboz cache blocks.  */
#define CBO_BLOCK_SIZE 64
#define CBO_BLOCK_MASK 63
#define CBO_BLOCK_SHIFT 6

    .attribute unaligned_access, 1

ENTRY (__memset_vector)
    .option push
    .option arch, +v
    .option arch, +zicboz

    mv   dst_ptr, dst
    beqz num, L(ret)

    andi value, value, 255
    beqz value, L(zero_path)

    li   tmp, SCALAR_THRESH
    bgeu tmp, num, L(prepare_scalar_fill)

    vsetvli vlmax, zero, e8, ELEM_LMUL_SETTING, ta, ma
    slli chunk, vlmax, 2
    bltu num, chunk, L(vector_fill)

    vmv.v.x vdata0, value
    vmv.v.x vdata1, value
    vmv.v.x vdata2, value
    vmv.v.x vdata3, value
L(vector_bulk_loop):
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
    beqz   num, L(ret)
    j      L(vector_tail)

L(prepare_scalar_fill):
    slli tmp, value, 8
    or   value, value, tmp
    slli tmp, value, 16
    or   value, value, tmp
    slli tmp, value, 32
    or   value, value, tmp
    j    L(scalar_fill_ptr)

L(vector_fill):
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma
    vmv.v.x vdata0, value
L(vector_loop):
    vse8.v  vdata0, (dst_ptr)
    sub     num, num, ivl
    add     dst_ptr, dst_ptr, ivl
    beqz    num, L(ret)
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma
    j       L(vector_loop)

L(vector_tail):
    vsetvli ivl, num, e8, ELEM_LMUL_SETTING, ta, ma
    j       L(vector_loop)

L(scalar_fill):
    mv   dst_ptr, dst
L(scalar_fill_ptr):
    li   tmp, 1
    beq  num, tmp, L(fill_1)
    li   tmp, 4
    bltu num, tmp, L(fill_2_3)
    li   tmp, 8
    bltu num, tmp, L(fill_4_7)
    li   tmp, 16
    bltu num, tmp, L(fill_8_15)
    li   tmp, 32
    bltu num, tmp, L(fill_16_31)
    li   tmp, 65
    bltu num, tmp, L(fill_32_64)
    j    L(fill_65_128)

L(fill_65_128):
    add  chunk, dst_ptr, num
    li   ivl, 8
L(fill_8_loop):
    sd   value, 0(dst_ptr)
    addi dst_ptr, dst_ptr, 8
    addi num, num, -8
    bgeu num, ivl, L(fill_8_loop)
    beqz num, L(ret)
    sd   value, -8(chunk)
    ret

L(fill_32_64):
    add  chunk, dst_ptr, num
    sd   value, 0(dst_ptr)
    sd   value, 8(dst_ptr)
    sd   value, 16(dst_ptr)
    sd   value, 24(dst_ptr)
    sd   value, -32(chunk)
    sd   value, -24(chunk)
    sd   value, -16(chunk)
    sd   value, -8(chunk)
    ret

L(fill_16_31):
    add  chunk, dst_ptr, num
    sd   value, 0(dst_ptr)
    sd   value, 8(dst_ptr)
    sd   value, -16(chunk)
    sd   value, -8(chunk)
    ret

L(fill_8_15):
    add  chunk, dst_ptr, num
    sd   value, 0(dst_ptr)
    sd   value, -8(chunk)
    ret

L(fill_4_7):
    add  chunk, dst_ptr, num
    sw   value, 0(dst_ptr)
    sw   value, -4(chunk)
    ret

L(fill_2_3):
    add  chunk, dst_ptr, num
    sh   value, 0(dst_ptr)
    sh   value, -2(chunk)
    ret

L(fill_1):
    sb   value, 0(dst_ptr)
    ret

L(zero_path):
    li   tmp, CBO_BLOCK_SIZE
    bltu num, tmp, L(scalar_fill_ptr)

    andi chunk, dst_ptr, CBO_BLOCK_MASK
    beqz chunk, L(zero_blocks)
    li   tmp, CBO_BLOCK_SIZE
    sub  chunk, tmp, chunk
    add  count, chunk, tmp
    bltu num, count, L(scalar_fill_ptr)
    vsetvli ivl, chunk, e8, ELEM_LMUL_SETTING, ta, ma
    vmv.v.x vdata0, x0
    vse8.v  vdata0, (dst_ptr)
    sub     num, num, chunk
    add     dst_ptr, dst_ptr, chunk

L(zero_blocks):
    srli count, num, CBO_BLOCK_SHIFT
    beqz count, L(zero_tail)
L(zero_block_loop):
    cbo.zero 0(dst_ptr)
    addi dst_ptr, dst_ptr, CBO_BLOCK_SIZE
    addi count, count, -1
    bnez count, L(zero_block_loop)
    andi num, num, CBO_BLOCK_MASK

L(zero_tail):
    beqz num, L(ret)
    j    L(scalar_fill_ptr)

L(ret):
    ret

    .option pop
END (__memset_vector)
libc_hidden_builtin_def (memset)
