# 2026中兴捧月赛题（初赛）

## 赛题方向：
RISC-V性能优化

## 赛题背景：

### 从嵌入式到高性能计算的跨越

RISC-V架构正加速突破传统嵌入式设备的应用边界，向高性能计算（HPC）、人工智能（AI）、大型服务器等复杂计算场景快速渗透。在这些对算力、延迟和吞吐量要求严苛的场景中，内存操作性能已成为制约系统整体效能的核心瓶颈。

作为Linux生态中最核心的基础运行库之一，GLIBC的memcpy、memset等内存操作函数广泛用于用户空间乃至系统各层组件中，其效率直接影响：

- 服务器启动与服务初始化的耗时
- Web服务、数据库等在线业务的QPS上限与延迟表现
- 大模型训练/推理等AI任务的计算效率

因此，针对memcpy、memset等核心内存操作函数的性能优化，不仅能为RISC-V架构在高性能计算场景的落地提供关键技术支撑，更兼具重要的工程实践价值与理论研究意义。

## 赛题简介(已知条件)：

本赛题要求参赛者针对支持 RV64GC + RVV + Zicboz 扩展的 RISC-V 64位高性能处理器环境，优化 GLIBC 中的核心函数： `memcpy`和 `memset`。

## 限制的提交语言:

C/汇编

## 赛题目标与任务说明：

基于 GLIBC 2.43 版本（赛题包见附件glibc-2.43.zip），对 memcpy 和 memset 函数进行高性能优化。参赛者需在保证功能完全正确的前提下，针对给定基准测试集，充分利用 RISC-V 架构特性实现极致性能。

本次优化重点考察选手对以下核心技术的理解与应用能力：

- 向量编程（RVV）模型与高效向量化实现
- 缓存块操作机制（Cache Block Operations）
- RISC-V 微架构流水线特性与内存访问优化
- 大块内存操作的边界处理与对齐策略

## 优化策略指引：

### 方法一：使用 C 语言 + RVV 向量扩展接口进行优化

- 使用如 __riscv_vle8_v_u8mf8, __riscv_vse8_v_u8mf8 这样的 RVV intrinsics（GCC/Clang 支持）；
- 结合 vsetvli 自适应返回值调优向量长度；
- 利用高带宽并行存储操作替代传统逐字节 store；

适合：

- 想兼顾可维护性和性能的选手；
- 有 RVV 向量化 C 编程经验；
- 需要快速测试硬件吞吐瓶颈。

### 方法二：使用手写 RISC-V 汇编，调用 RVV / Zicboz 指令集加速 memset

- 汇编手写接口，调用 RVV 加速 store 清零/填充；
- 针对 value == 0 的 memset 情况，启用 cbo.zero（Zicboz）指令，一条指令清空整块 Cache Line；
- 精细管理边界对齐、尾部处理、流水线调度等微架构细节，实现极致性能。

适合：

- 对底层优化、微架构熟悉的选手；
- 追求最大吞吐与性能极限；
- 能精准控制 loop unrolling、pipeline latency 等细节。

### 补充说明

选手也可混合使用上述两种方法，或探索其他创新优化手段，例如：

- RVV 与标量指令的混合调度
- 基于 Cache Line 对齐的特殊处理路径
- 利用 RISC-V 其他相关扩展（如向量压缩、向量分段加载等）
- 针对不同数据规模的自适应优化策略

核心要求：在确保功能正确性、边界条件完备性的前提下，最大化利用 RISC-V 架构的向量计算能力和内存子系统特性，实现基准测试集上的性能突破。


## 评分规则:

总分得分构成如下：
$$
\text{Total Score} = (S_{\text{memcpy}} \times 0.3) + (S_{\text{memset}} \times 0.3) + (\text{代码创新性} \times 0.2) + (\text{优化思路} \times 0.2)
$$

1. Memcpy 子分

   bench-memcpy (40%): 基础得分。

   bench-memcpy-random (40%): 高权重。考察在无法预测长度时的综合调度能力（Scalar vs Vector 切换）。

   bench-memcpy-large (20%): 考察 RVV 峰值带宽。

2. Memset 子分

   bench-memset (20%): 常规填充。

   bench-memset-zero (40%): 极高权重。考察是否有效利用 Zicboz 扩展对小/中块内存清零的加速。

   bench-memset-large (20%): 大块常规填充。

   bench-memset-large-zero (20%): 大块 Zicboz 循环清零效率。

### 计分公式

单项加速比:

$$
Speedup = \frac{Time_{GLIBC-Base}}{Time_{Submission}}
$$

注：GLIBC-Base 为未开启 RVV/Zicboz 优化的通用版本。

注：对于包含多个子测例的 benchmark（如 bench-memcpy），取所有子测例加速比的平均数作为该项得分。


## 提交介绍

### 数据流

   Input: Benchmark 程序内部生成随机数据或特定模式数据。

   Output: 程序标准输出（stdout）打印的 JSON 性能报告。


## 提交规范

请将所有源码及算法优化文档（截止比赛前只需提交一份终版即可，算法优化文档用于阐述优化思路）打包提交。修改riscv架构下的memcpy-vector.S/memcpy-vector.c、memset-vector.S/memset-vector.c文件，编译GLIBC，结果提交前必须通过test-memcpy/test-memset正确性测试。

benchtest编译参照（https://elixir.bootlin.com/glibc/glibc-2.43/source/benchtests/README）。

参赛者需提交 `submission.zip`，目录结构如下：

实现文件：

```
submission/
|—— src/
|    |—— memcpy-vector.S/memcpy-vector.c        # 优化实现源码
|    |—— memset-vector.S/memset-vector.c         # 优化实现源码
|—— docs/
|    |—— Optimization_Report.pdf                # 详细的算法优化报告
```

## 目标环境与指令集约束：

- 架构：RISC-V 64-bit (RV64)。
- 编译测试环境为QEMU，详细环境搭建手册见附件（QEMU-RISC-V搭建指导手册）。

## 限制语言及版本：

- 开发语言：不限制编程语言，推荐C语言/汇编语言。
- 架构：RISC-V 64-bit（RV64GC）
- 推荐向量扩展（RVV）：假设 VLEN >= 128 bit，支持 RVV 1.0
- 推荐Zicboz 扩展：假设 Cache Line 为 64 字节，支持 cbo.zero
- 编译器支持：
    - GCC >= 14.3 或 Clang >= 14
    - Flags: -march=rv64gcv_zicboz -mabi=lp64d -static

## 编程接口规范

- 文件名：必须为 memset-vector.S 或 memset-vector.c；
- 若使用RVV intrinsics：可命名为 memset-vector.c；
- 若使用纯汇编：命名为 memset-vector.S；

## 全局符号导出要求：

必须导出  `__memset_vector` 供链接器调用。

或：

__attribute__((visibility("default"))) void *__memset_vector(void *s, int c, size_t n);

memcpy系列函数优化接口规范同上。


## 优化建议与注意事项
### 优化建议

1.  Zicboz 块大小检测：`cbo.zero` 指令依赖于硬件的 Cache Block Size（通常在 `mhartid` 或设备树中，但在用户态 GLIBC 中通常通过 `sysconf` 或预设宏获取）。本赛题假定 Block Size 为 64 字节，选手代码中可硬编码或动态探测,也可以默认64字节。
2.  RVV VSETVLI 策略：充分利用 `vsetvli` 的返回值来处理循环，避免手动编写剩余字节处理代码。
3.  Hybrid 策略：对于极小的拷贝（如 < 16 字节），启动 RVV 可能不如直接使用通用寄存器（Scalar）快。选手需通过实验找到最佳的标量/向量切换阈值。
4.  Memset Zero 分支：在 `memset` 入口处快速判断设置值是否为 0。若为0立即跳转到 Zicboz 优化路径；否则走 RVV 填充路径。
5.  代码查重：严禁直接抄袭现有开源实现（如 LLVM libc 或最新的 GLIBC RVV patch），必须体现针对赛题权重的特定优化策略。
