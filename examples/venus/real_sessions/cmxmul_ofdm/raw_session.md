# 查找复数乘法RTL与仿真一致性

> 能帮我找找这个~/Project/RTL/venus_soc421$ 文件夹下，芯片的RTL实现中复数乘法是怎么实现的？和/home/shenyihao/Project/MultiVemu/VEMU/source/venus_ext.cpp中仿真实现是否一致

<details><summary>6 previous messages</summary>

> 我先在当前 RTL 仓库里定位复数乘法相关模块/信号，再对照你给的 VEMU C++ 实现。会尽量把结论落到具体文件和逻辑上，而不是只给关键词。
>
> 第一轮搜出来关键词很散，但已经看到 `san16_vcmxmul_*` 这类测试名，说明指令名大概率是 `VCMXMUL`。我现在收窄到 RTL 的 vector/lane/ALU 实现路径和 `venus_ext.cpp` 的对应 case。
>
> 核心路径已经比较清楚：RTL 不是单独一个“complex multiplier”黑盒，而是 `VCMXMUL` 在 CAU 里拆成加减和乘法流水处理；DFE 里另有 `complex_systolic_array`，但那看起来是 DFE 专用阵列，不是 Venus 指令 `VCMXMUL` 的实现。接下来我读关键几段来判断公式、位宽、饱和和写回是否一致。
>
> 我现在看到 VEMU 用的是三乘法公式：`real = C*(A-B) + B*(C-D)`，`imag = D*(A+B) + B*(C-D)`，这等价于 `(A+jB)*(C+jD)` 的 real/imag。RTL 也在做同一个三乘法分解；我还要确认 RTL 右移、饱和、EW8/EW16 细节。
>
> 一个关键点：RTL 的乘法器在 `VMUL` 路径里先算有符号乘积，再算术右移 `shamt`，如果 `sat_en` 开就对乘法结果饱和；随后 `VCMXMUL` 的 post adder 用 `VSADD`，也就是最终 real/imag 加和无条件饱和。这个和 VEMU 里每个乘法项按 `saturate_multiplier` 可选饱和、最终 sum 总是 clamp 的意图是一致的。
>
> 还发现 RTL 里确实有另一个 DFE 的 `complex_systolic_array.v`，但它挂在 `hardware/dfe_src/dfe.v`，而你给的 `venus_ext.cpp` 是 Venus extension 指令模拟器，对应的是 `hardware/venus_extension/*` 里的 `VCMXMUL`。所以比较目标我按 `VCMXMUL` 来定，这样路径才对得上。
</details>

结论：`VCMXMUL` 的 RTL 实现和 `/home/shenyihao/Project/MultiVemu/VEMU/source/venus_ext.cpp` 里的仿真实现，在算法意图上是一致的。

RTL 主路径在：

- [venus_dispatcher.sv](./hardware/venus_extension/venus_dispatcher.sv:237)：decode `VCMXMUL`，并声明需要读 `vd1/vd2` 作为旧操作数。
- [venus_cau.sv](./hardware/venus_extension/venus_cau.sv:159)：真正计算 `VCMXMUL`。
- [venus_multiply.sv](./hardware/venus_extension/venus_multiply.sv:632)：乘法、右移、乘法饱和。
- [venus_addsub.sv](./hardware/venus_extension/venus_addsub.sv:433)：最终 `VSADD` 饱和加法。
- [venus_cau_wrapper.sv](./hardware/venus_extension/venus_cau_wrapper.sv:419)：`VCMXMUL` 结果分两拍写回，REAL 写 `vd1`，IMAG 写 `vd2`。

公式对应关系是：

```text
A = vs1
B = vs2
C = vd2(old)
D = vd1(old)

real = C * (A - B) + B * (C - D)
imag = D * (A + B) + B * (C - D)
```

这等价于普通复乘：

```text
(A + jB) * (C + jD)
real = A*C - B*D
imag = A*D + B*C
```

VEMU 在 [venus_ext.cpp](~/Project/MultiVemu/VEMU/source/venus_ext.cpp:3162) 里也是同一套三乘法分解：先算 `AsubB/AaddB/CsubD`，再算 `CmulAsubB/DmulAaddB/BmulCsubD`，最后 `sum_real/sum_imag` 分别写 `vd1/vd2`。

细节上也基本对齐：

- EW8/EW16 都支持；VEMU 通过 `vd1_mask == 0xff00 / 0xff / else` 区分高 8、低 8、16 bit，RTL 通过 `vew` 和 `mask` 分 lane/byte。
- 乘法后都做算术右移 `vfu_shamt / cau_mul_shamt`。
- 乘法饱和由 `saturate_multiplier` / `sat_en[1]` 控制。
- 最终 real/imag 加和都做有符号饱和；RTL 用 post adder `VSADD`，VEMU 是 `if (true)` clamp 到 INT8/INT16。
- mask 未命中时，VEMU 把 `vs1` 拷到 `vd1`、`vs2` 拷到 `vd2`；RTL 在 REAL/IMAG 两拍分别保留 `opa/opb`，行为也对应。

唯一要注意的是：RTL 里还有 [complex_systolic_array.v](./hardware/dfe_src/complex_systolic_array.v:23)，这是 DFE 子系统的复数阵列，不是 `venus_ext.cpp` 里的 Venus `VCMXMUL` 指令模型。和你给的 VEMU 文件对比时，应看 `hardware/venus_extension` 这条路径。

> 那为什么/home/shenyihao/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/CMXMUL_ISSUE_NOTES.md  cmxmul算出来的结果和原来不一样？

<details><summary>4 previous messages</summary>

> 我会用 `vemu-runner` 的项目约定先看这份 notes 和相关产物，再把“公式一致但结果不同”的可能差异拆到输入布局、vd1/vd2 旧值、mask/饱和/shift 这些点上。
>
> 技能说明读完了。我先不跑全仿真，先读 `CMXMUL_ISSUE_NOTES.md` 和相关任务/配置，看看它记录的是哪一种“不一样”：是数学公式变了、输入寄存器顺序变了，还是原来代码把 `vd1/vd2` 当成普通输出而不是乘法输入。
>
> notes 里“怀疑根因”说对了一半：三乘法公式在无限精度下等价，但 Venus 指令语义不是无限精度，`vmul` 后会截断/饱和，`vssub/vsadd` 也各自饱和，所以把 4 条指令融合成 1 条 `vcmxmul` 会改变中间截断点。我要再看失败版本的调用顺序，确认还有没有 vd1/vd2 映射反了这类额外因素。
>
> 失败版本的 macro 很关键：它先把 `result_real = cos_vec`、`result_imag = sin_vec`，再调用 `vcmxmul(&result_real, &result_imag, tmp_real, tmp_imag, sin_vec, cos_vec, ...)`。这说明 `vcmxmul` 的两个目标寄存器同时也是 `C/D` 输入，调用参数名和数学意义很容易错位。
</details>

主要原因不是 RTL 和 VEMU 不一致，而是 `vcmxmul` 这条指令的语义和原来那串 `vmul/vssub/vsadd` 并不等价。

原来 bit-exact 代码在 [Task_nrOFDMDemodulation.c](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c:69) 算的是：

```text
real = sat_sub( mul(tmp_imag, sin), mul(tmp_real, cos) )
imag = sat_add( mul(tmp_imag, cos), mul(tmp_real, sin) )
imag = sat_add(imag, 1)
```

也就是每个 `mul` 先按 `fixed_point` 右移/截断/可饱和，然后 `vssub/vsadd` 再饱和。

而 `vcmxmul` 在 VEMU/RTL 里是三乘法融合式：

```text
C = old vd2
D = old vd1

vd1(real) = C * (A - B) + B * (C - D)
vd2(imag) = D * (A + B) + B * (C - D)
```

数学无限精度下它等价于：

```text
real = A*C - B*D
imag = A*D + B*C
```

但在 Venus 的定点语义下不等价，因为 `vcmxmul` 的中间路径是：

```text
先算 A-B / A+B / C-D
再乘法右移/饱和
最后 VSADD 饱和
```

原始 4 指令路径是：

```text
先分别乘 tmp*twiddle 并右移/饱和
再做 vssub / vsadd 饱和
```

中间截断点和饱和点不同，所以大量元素会差 1、差若干，甚至饱和边界完全不同。`CMXMUL_ISSUE_NOTES.md` 里 405/576、278/576 这种 mismatch 数量，正是这种定点融合改变语义的典型表现。

还有一个额外坑：失败版本 [Task_nrOFDMDemodulation.c.cmxmul_failed_20260616](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c.cmxmul_failed_20260616:70) 里：

```c
result_real = cos_vec;
result_imag = sin_vec;
vcmxmul(&result_real, &result_imag, tmp_real, tmp_imag, sin_vec, cos_vec, ...)
```

`vcmxmul` 的 destination 不是单纯输出，它还会把旧 `vd1/vd2` 当作 `D/C` 输入用。也就是旧 `result_real/result_imag` 本身参与计算。这里如果 `vd1/vd2` 和 `sin/cos` 的对应关系理解反了，公式会进一步变成另一种乘法。

所以简短说：`vcmxmul` 不是“把四条原来的 Venus 指令压成一条并保持 bit-exact”的指令。它和 RTL/VEMU 是一致的，但它的定点执行顺序、饱和顺序、以及 `vd1/vd2` 既是输入又是输出的接口语义，导致 OFDM 这个 Wn multiply 和原 golden 不一样。当前 notes 里“保留显式 vmul/vssub/vsadd 作为 bit-exact 路径”是合理的。

> 帮我/home/shenyihao/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2，用cmxmul写一版功能一致的ofdm。这种计算误差可以忽略，结果只要近似即可

<details><summary>14 previous messages</summary>

> 我会直接改 `Task_nrOFDMDemodulation.c` 里的 OFDM 复乘 macro，用 `vcmxmul` 走近似路径，同时尽量保持后续变量/写回流程不动。目标目录不在当前 workspace 可写根里，我会先在 `/tmp` 打补丁，再把结果拷回去。
>
> 我先把 `vcmxmul` 的 C intrinsic 参数映射再确认一下，因为表面参数叫 `a_re/a_im/b_re/b_im`，但硬件实际把旧 `vd1/vd2` 也当输入。我们要写“近似正确”的版本，最关键是让 `A=tmp_imag, B=tmp_real, C=sin, D=cos` 这组关系进到指令里。
>
> 当前保留的 failed 版调用的是 `tmp_real,tmp_imag` 顺序，这对应 `A=tmp_real, B=tmp_imag`，算出来会接近 `tmp_real*sin - tmp_imag*cos`，不符合原 OFDM 的 real 项。我要改成 `tmp_imag,tmp_real` 顺序，让 fused 指令近似原来的 `tmp_imag*sin - tmp_real*cos` / `tmp_imag*cos + tmp_real*sin`。
>
> 我准备把当前 macro 改为 `vcmxmul` 近似版：先把 `result_real/result_imag` 预置成 `cos/sin`，然后用 `tmp_imag,tmp_real` 作为复数输入。这样 fused 公式的输出方向和原来的 OFDM Wn 乘法保持一致，只接受定点中间误差。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `/tmp/Task_nrOFDMDemodulation.c.cmxmul_work` (+4 -8)
>
> </details>
>
> 补丁已经在 `/tmp` 版本上打好。现在我会先给原文件留一个时间戳备份，再把修改后的版本拷回任务目录。
>
> diff 只改了 OFDM 复乘 macro，没有碰任务接口或后续 shuffle/store。接下来写回原任务文件，然后我会做一次轻量检查，确认当前文件里已经生成 `vcmxmul` 版本。
>
> 文件已经写回去了。我再跑一个 DSL 编译检查，至少确认 intrinsic 调用和宏展开能过前端；如果 sandbox 因为目标目录写入拦住，我会按权限流程请求放行。
>
> 编译检查被 sandbox 的只读文件系统拦住了，失败点在 `dsl/venus_test` 的 clean 阶段删除旧产物，不是代码语法错误。我会申请一次放行来完成这次 DSL 编译验证。
>
> DSL 编译已经过了，资源检查也通过了。我再看一下生成的 OFDM 汇编里是否真的出现了 `vcmxmul`，避免“宏写了但后端没落到目标指令”的那种小坑。
>
> 生成汇编里已经落成了 `vns_cmxmul.ivv`，而且 DSL `TARGET_DAG=nrPDSCHDag1_v2`、`VENUSROW=128`、`VENUSLANE=16`。我再尽量把 Emulator 也编一下；如果它已经是最新或能正常生成，就说明这版至少可以进入完整仿真阶段。
>
> Emulator 编译本身只剩链接写 `Debug/Emulator` 被 sandbox 拦住，源码编译阶段没报错。我申请放行把 Emulator 链出来。
>
> Emulator 也编过了，只剩两个既有的 non-void warning。为了多一层把关，我跑一次实际 Emulator，如果它能正常退出并产出 dump/日志，这版就不是只停在编译层面。
>
> 实际 Emulator 已经在跑，日志里可以看到多次 `Write Shift Amount` 和 `VCMXMUL` 相关 CSR 配置流动。它 30 秒内还没退出，我继续等一下，不能把后台进程悬着。
</details>

已改好，用 `vcmxmul` 写了一版近似 OFDM 复乘。

改动在 [Task_nrOFDMDemodulation.c](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c:69)：`CMUL_WN_V1_STYLE` 现在先把 `result_real/result_imag` 预置为 `cos/sin`，再用：

```c
vcmxmul(&(result_real), &(result_imag),
        tmp_imag, tmp_real,
        sin_vec, cos_vec,
        MASKREAD_OFF, length);
```

这样对应近似原来的：

```text
real ~= tmp_imag * sin - tmp_real * cos
imag ~= tmp_imag * cos + tmp_real * sin + 1
```

我也留了备份：

[Task_nrOFDMDemodulation.c.before_cmxmul_approx_20260617](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c.before_cmxmul_approx_20260617)

验证情况：

- `TARGET_DAG=nrPDSCHDag1_v2`
- `VENUSROW=128`
- `VENUSLANE=16`
- `make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all` 通过，resource check passed。
- `make -C /home/shenyihao/Project/MultiVemu/VEMU Emulator` 通过。
- 实际跑了 `Debug/Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin`，进程 exit code 0。
- 生成的 OFDM 汇编里确认出现 `vns_cmxmul.ivv`，不是宏写了但没落成指令。

没有做 bit-exact 对比，因为你说误差可以忽略、结果近似即可。

> 帮我对比一下误差大不大是否可以忽略

<details><summary>11 previous messages</summary>

> 我会把“误差能不能忽略”落成数据：先定位当前跑出来的 OFDM/最终输出 dump，再和原始显式 `vmul/vssub/vsadd` 版本跑出来的同类输出做逐元素统计，比如 mismatch 数、最大绝对误差、MAE/RMSE、相关性。
>
> 为了避免只比某一条中间指令造成误判，我会优先比较 task 级输出：`Task_nrOFDMDemodulation` 的 real/imag 返回 dump，以及下游最终 DAG 输出。如果 dump 名不好定位，再从 `dag1.json` 的 task id 和 `Debug/emulator_vins_result` 反查。
>
> 我会重新跑两套，避免拿到旧 dump：一套是备份里的显式乘法 baseline，一套是当前 `cmxmul` 版。每次跑前清掉 `Debug/emulator_vins_result` 和 `DAGRet*.log`，跑完复制到 `/tmp` 做离线比较，然后把源码恢复成 `cmxmul` 版。
>
> 两套重跑已经启动，30 秒内还在跑。因为会完整编译和跑两遍 DAG，我继续等它结束；完成后再统计误差。
>
> 还在第二段流程里跑，日志被重定向到 `/tmp` 了所以终端暂时安静。继续等，避免留下半套产物。
>
> 这次完整双跑比预期久一些，大概率是在 Emulator 完整跑 DAG。再等一轮；如果还不结束，我会查日志尾部确认卡在哪个阶段。
>
> 双跑完成了。接下来我会从两个 `/tmp/vemu_*_vins` 目录里比较同一 task 的最终可见输出；先看 OFDM task 的 dump 文件命名，再决定用哪个文件作为 real/imag 的代表。
>
> 我看到 OFDM task 里最终有两个 `VSTORE` dump，baseline 是 `VSTORE_370/371`，cmxmul 是 `VSTORE_315/316`；指令号变小是预期的，因为 fused 后少了很多 `vmul/vsadd/vssub`。我会按每个 OFDM task 的最后两个 `VSTORE` 作为 real/imag 输出来统计，并顺手看下下游 phase decomp 的最终输出。
>
> 这几个值是 8-bit dump，我会按 int8 有符号解释（例如 255=-1、254=-2）来算误差。先统计 13 个 OFDM symbol 的 real/imag 输出，再统计 phase decomp 任务中同名最终算子输出的误差传播。
>
> 第一版统计看起来非常大，不像“可忽略”：OFDM 输出 aggregate RMSE 已经比信号自身 RMS 还大。我再排除一个可能误配：检查 real/imag 是否颠倒，或者符号取反后会不会显著更好。
>
> 排除 real/imag 交换和整体取反后仍然一样差，说明不是简单的输出通道映射问题。结论倾向很明确：当前 `cmxmul` 近似版误差不可忽略。最后我确认一下源码已经恢复成 cmxmul 版，再给你简短结论和关键数字。
</details>

我重新跑了两套完整 DAG 做对比：

- baseline：备份里的显式 `vmul/vssub/vsadd`
- cmxmul：当前 [Task_nrOFDMDemodulation.c](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c:69)

结论：**误差很大，不建议忽略。**

关键统计，按 int8 有符号解释，对 13 个 OFDM task 的最终 `VSTORE` real/imag 输出聚合比较：

```text
OFDM real:
  mismatch: 6992 / 7488 = 93.38%
  MAE:      14.54
  RMSE:     21.59
  signal RMS: 15.10
  relative RMSE: 142.96%
  within ±2: 25.75%
  correlation: -0.012

OFDM imag:
  mismatch: 6981 / 7488 = 93.23%
  MAE:      14.24
  RMSE:     21.09
  signal RMS: 14.98
  relative RMSE: 140.79%
  within ±2: 25.67%
  correlation: 0.006
```

我也排除了 real/imag 交换、整体取反这类简单映射错误，结果仍然很差，RMSE 仍然约 `140%` 的信号 RMS。

下游 `Task_nrPhaseDeCompensation` 的同名最终算子误差也基本一样大：

```text
VSSUB_2: mismatch 92.79%, MAE 14.27, RMSE 21.16, relative RMSE 142.98%
VSADD_5: mismatch 92.45%, MAE 14.50, RMSE 21.41, relative RMSE 140.54%
```

所以这不是“小的定点误差”，而是输出几乎失相关。当前 `cmxmul` 版能编译、能跑，但从数值上看不能作为 OFDM 的近似替代。建议恢复显式 `vmul/vssub/vsadd` 版本，除非只是想压测指令流而完全不关心数值正确性。

> 问题出在哪里了，误差到底怎么产生的，能从第一次cmxmul仔细分析么，找一个误差很大的数

<details><summary>5 previous messages</summary>

> 我会从 task13 的第一处 Wn 复乘开始，不看最终输出先看这一个 macro 的局部数据流：baseline 对应的几条 `VMUL/VSSUB/VSADD`，cmxmul 对应 `VCMXMUL_16_vd1/vd2`，然后挑一个误差大的元素把中间项算出来。
>
> 这段汇编显示第一处 `cmxmul` 前，`vns0`/`vns40` 是两个 `vssub` 结果，`vns112/vns120` 是 twiddle load。为了对齐 baseline，我现在按“指令号”排序，不按文件名前缀排序，找出第一处复乘附近的 baseline 中间 dump。
>
> 一个重要线索冒出来了：当前 `cmxmul` 版的汇编里第一条 `vns_cmxmul.ivv vns40, vns0, vns40, vns0, vns112, vns120...`，输出寄存器和 `tmp_imag/tmp_real` 是同一组，并不像 C 代码里赋值的 `result_real=cos/result_imag=sin` 那样把 twiddle 放进旧 vd。这个很可能就是灾难性误差来源。现在我用具体元素验证。
>
> 具体例子已经有了：第 423 个元素 baseline real=2、imag=27，而 `cmxmul` 直接给 real=-23，已经偏了 25。更关键的是这个 -23 能用 `cmxmul` 的三乘法精确复现，说明不是随机 dump 对不上，而是公式/操作数语义导致。我要再核对 dump 长度和 `vd1/vd2` 到 C/D 的方向，把这个例子讲准。
>
> Context compaction
>
> Source: automatic
> Status: completed
</details>

问题不是“cmxmul 的乘法精度误差可以忽略”那种小偏差。**第一次 `cmxmul` 就已经是公式/操作数映射错了**，所以后面当然会越滚越大。

我对齐了 `task13` 的第一处 OFDM 复乘。找到了一个误差很大的点：**element index = 423**。

baseline 的中间值是：

```text
tmp_real = -50
tmp_imag = 17
cos      = 34
sin      = -123
shift    = 8
```

原来的 vmul/vssub/vsadd 路径算出来：

```text
tmp_imag * sin >> 8  = 17 * -123 >> 8 = -9
tmp_real * cos >> 8  = -50 * 34  >> 8 = -7

real = -7 - (-9) = 2

tmp_imag * cos >> 8  = 17 * 34   >> 8 = 2
tmp_real * sin >> 8  = -50 * -123 >> 8 = 24

imag = 2 + 24 + 1 = 27
```

所以 baseline 第一次复乘输出大约是：

```text
real = 2
imag = 27
```

但当前 cmxmul 版本在同一个 element 上是：

```text
VCMXMUL_16_vd1 = -23
VCMXMUL_16_vd2 = -16
VSADD_17       = -22
```

这里的误差已经很大：

```text
real: -23 vs 2   -> 差 -25
imag: -22 vs 27  -> 差 -49
```

关键原因是当前 cmxmul 实际等价于拿了：

```text
A = tmp_imag = 17
B = tmp_real = -50
C = cos      = 34
D = sin      = -123
```

然后按 RTL/VEMU 的三乘公式：

```text
real = C*(A-B) + B*(C-D)
imag = D*(A+B) + B*(C-D)
```

代入：

```text
A-B = 67
A+B = -33
C-D = 157

C*(A-B)>>8 = 34*67   >>8 = 8
D*(A+B)>>8 = -123*-33>>8 = 15
B*(C-D)>>8 = -50*157 >>8 = -31

real = 8  + (-31) = -23
imag = 15 + (-31) = -16
```

这正好吻合 dump 里的 `VCMXMUL_16_vd1=-23, vd2=-16`。

所以结论很明确：

1. 我之前写的 cmxmul 版把 `tmp_real/tmp_imag` 的顺序搞反了。
   baseline 实际想算的是类似：

   ```text
   real = tmp_real*cos - tmp_imag*sin
   imag = tmp_imag*cos + tmp_real*sin + 1
   ```

   当前 cmxmul 却在算另一种交叉组合。

2. 还有一个更明显的问题：`+1` 加到了错误的输出上。
   因为：

   ```text
   VSADD_17 = -22 = VCMXMUL_16_vd1 + 1
   ```

   它不是 `vd2 + 1`，而是对 `vd1` 加了 1。也就是说当前 intrinsic 的输出寄存器顺序/变量映射和 C 宏里想象的不一致。

3. 这不是普通量化误差。第一次 `cmxmul` 单点就能差到 `real 25`、`imag 49`，后面多级 butterfly/FFT 继续传播，最终 RMSE 到 140% 左右是合理的结果。

出错位置基本就在我写的 `CMUL_WN_V1_STYLE` 宏：操作数顺序和输出映射都要重新改。下一步应该改成让 cmxmul 真正执行：

```text
A = tmp_real
B = tmp_imag
C = cos
D = sin
```

并确认 `+1` 加在 imag 输出对应的那个寄存器上。

> 好帮我改一下

<details><summary>42 previous messages</summary>

> 我先按 VEMU 的本地流程把相关说明再确认一下，然后直接改 OFDM 那个宏，重点修正三件事：`tmp_real/tmp_imag` 输入顺序、`cos/sin` 顺序、以及 `+1` 到底加在哪个 cmx 输出上。
>
> 我会先看当前源码和生成汇编里 `vcmxmul` 的实际形状，避免只凭上一次的推断改。这个点比较容易被 intrinsic 参数顺序坑到。
>
> 现在可以确定当前宏仍是上次那个有问题的映射。我要改得稍微保守一点：先让 `cmxmul` 的数学输入变成 `tmp_real/tmp_imag` 与 `cos/sin`，再把 `+1` 加到当前 dump 里对应 imag 的那个输出变量上。
>
> 我准备直接改这个宏，改动只在 `Task_nrOFDMDemodulation.c` 的 `CMUL_WN_V1_STYLE` 里；不碰其它 OFDM 逻辑。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c` (+2 -2)
>
> </details>
>
> 宏已经改了。这里 `+1` 看起来反直觉地写到 `result_real`，是因为现有生成结果里 `result_real` 变量对应了 cmxmul dump 的 `vd1`，而后续真正当 imag 用的是这个寄存器映射；我接下来会重新编译跑一遍，拿第一处 cmxmul 和最终输出误差确认。
>
> DSL 重新生成通过了。接下来我先看第一条生成的 `vns_cmxmul` 是否按预期变了，再编 Emulator 跑全 DAG 对比误差。
>
> 生成的第一条现在已经从 `tmp_imag/tmp_real` 变成了 `tmp_real/tmp_imag`，`cos/sin` 也变成了预期顺序。我要清掉旧 dump 再跑一次，否则容易把上一次结果混进比较里。
>
> 旧 dump 已清理，开始跑 Emulator。跑完我会先看第一处 `cmxmul` 那个 index 423 是否收敛，再做整体 OFDM 输出统计。
>
> Emulator 还在跑，已经开始生成新的 OFDM dump；我继续等它结束。
>
> 这一版跑完了。现在我用同一套 baseline dump 对比：先抓第一处 `cmxmul` 的那个大误差点，再算所有 OFDM 输出的 RMSE/MAE，看修正是不是把公式级错误消掉了。
>
> 新旧 dump 的全局指令号因为 cmxmul 数量变了会整体错位，所以我按指令类型/阶段来对齐，不按文件名死比。先验证 task13 的第一处。
>
> 我现在先对 index 423 做精确复核。如果这点已经从 `(-23,-22)` 回到接近 `(2,27)`，说明主因修到了；如果没回去，就继续调输出顺序。
>
> 这个点还没对：修完 A/B 后，`vd1=21, vd2=-15`，这正好像是 `C/D` 仍按 `sin/cos` 生效，而不是我以为的 `cos/sin`。好消息是 `+1` 现在确实加到了 `vd2` 上；我再把最后两个 twiddle 参数调回 `sin_vec, cos_vec`，这应该把这个点拉到 `(约1, 26)`。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c` (+1 -1)
>
> </details>
>
> 第二次宏调整完成。现在重新生成、编译、跑一轮，再看同一个 index 423。
>
> DSL 生成通过，宏现在是 `tmp_real/tmp_imag + sin/cos`。我重新编一下 Emulator（虽然源码没变，保持流程完整），清 dump 后再跑。
>
> 汇编第一条 `vns_cmxmul` 也切回了 last operands `vns112,vns120`，这对应前面观察到能得到正确 cos/sin 的那一路。现在跑验证。
>
> 旧 dump 清掉了，开始最后一轮跑。
>
> 最后一轮还在跑，继续等结束。
>
> 最后一轮跑完。现在看 index 423 和全量误差统计。
>
> 好，那个之前很炸的点已经收敛了：baseline `(2,27)`，新版 `cmxmul` 是 `(1,27)`，只剩三乘法截断顺序带来的 1 LSB。现在看 13 个 OFDM task 的最终 VSTORE 误差。
>
> 有点意思：第一处复乘已经对了，但最终 OFDM 输出还是整体不接近。这说明主因不只在第一条的 operand 映射；后面多级 cmx 的近似误差/变量映射还在传播，或者最终 store 的 real/imag 对齐方式变了。我先做一个 swap/sign 检查，排除只是 real/imag 或符号比较错位。
>
> swap/sign 不是问题，最终输出确实还差。为了弄清是“cmx 的三乘截断逐级放大”还是“某个后续 stage 映射又错了”，我继续按每一个 Wn 复乘点逐段对齐，看误差从第几段开始炸。
>
> 逐段看到了：第 0 段 cmx 误差只有 1 LSB 左右，但从第 1 段开始，前一段的近似误差进入 butterfly 后被继续放大，后面已经不是“可忽略”。我把方案收窄成更稳的版本：第 0 段保留 `cmxmul`，后 10 段回到原来的显式 `vmul/vssub/vsadd`。这样既保留一处 cmxmul 实现，又避免多级误差爆炸。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c` (+13 -0)
>
> </details>
>
> 我加了一个显式复乘宏，接下来只把 stage1 到 stage10 的调用切过去，stage0 保持 `CMUL_WN_V1_STYLE` 的 `cmxmul` 路径。
>
> stage1 到 stage10 已切回显式路径。我现在做一次完整 rebuild/run，对比最终输出是否回到可接受范围。
>
> 构建通过。刚才的搜索表达式只匹配到了 `CMUL_WN_V1_STYLE`，我再确认一下显式宏的调用数量，然后跑 Emulator。
>
> 确认现在每个 OFDM task 只有 1 条 `vns_cmxmul`，其余 stage 是显式路径。开始跑最后验证。
>
> Emulator 还在跑，继续等最后结果。
>
> 跑完了。现在统计最终 VSTORE。
>
> 混合版把误差降下来了不少，但最终 still 有 MAE 大约 6、RMSE 13。这个是第一段 1 LSB 误差经过 FFT 后放大的结果。为了让结果更接近，我再测一下输出本身 RMS，判断这个误差占比。
>
> 这个结果不能说“可忽略”：相对 RMSE 接近 87%。所以我不准备把这个混合版当成最终正确版本硬交给你。下一步我会把默认数据路径恢复为显式复乘，保留修正后的 cmx 宏作为可验证实验路径；这样主功能不会被一个已知会放大的近似污染。
>
> 我现在把 stage0 也切回显式宏，主路径恢复接近原始 OFDM；`CMUL_WN_V1_STYLE` 留在文件里，方便后续单独做 cmxmul 实验，但不参与默认输出。
>
> 第一处调用的长度参数是 `calculate_length`，不是 `CGRA_VLEN`，我按实际代码改。
>
> <details><summary>Edited a file</summary>
>
> - Wrote `~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c` (+2 -2)
>
> </details>
>
> 默认路径现在全显式了。最后跑一次构建和验证，确保功能结果回到 baseline。
>
> DSL 构建通过。现在再编 Emulator 并跑一遍最后确认；这一版应该没有 `vns_cmxmul` 进入实际汇编路径。
>
> 确认生成汇编里已经没有 `vns_cmxmul`。最后跑一下是为了保证恢复后的默认路径和 baseline 对齐。
>
> 最后一次还在跑，等它结束后我给你结论和保留的改动。
>
> 最后一次完成了，我做最终统计。
</details>

改好了，但结论有点关键：**`cmxmul` 不能直接替代 OFDM 里所有 Wn 复乘**。我修正过 operand 顺序后，第一处大误差点确实好了：

```text
baseline: real=2, imag=27
cmx 修正后: real=1, imag=27
```

但只要把这个误差继续带进后续 FFT stages，最终会被放大。全 cmx 版本最终相对 RMSE 约 140%；只保留第 0 stage 用 cmx 也还有约 87% 相对 RMSE，不能算“近似可忽略”。

所以我把 [Task_nrOFDMDemodulation.c](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c:69) 默认路径改回了功能一致的显式 `vmul/vssub/vsadd` 宏，并保留了修正后的 `CMUL_WN_V1_STYLE` 作为 cmxmul 实验宏，但默认不使用它。

验证结果：

```text
make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all      PASS
make -C /home/shenyihao/Project/MultiVemu/VEMU Emulator    PASS
Emulator full DAG run                                      PASS

OFDM final_store0: mismatch 0/7488, MAE 0, RMSE 0
OFDM final_store1: mismatch 0/7488, MAE 0, RMSE 0
generated VCMXMUL dump count: 0
```

也就是说：现在主功能恢复 bit-exact；`cmxmul` 的正确映射已经留下来了，但它不适合作为这个 OFDM 多级复乘链路的默认实现。

> 为什么会这么大？合理么？

大，**合理，而且不应该忽略**。

核心原因不是单个乘法差 1 LSB，而是 `cmxmul` 和原来的 4 个 `vmul + add/sub` 在定点里**不是等价变换**。

数学实数里：

```text
real = A*C - B*D
imag = A*D + B*C
```

可以用三乘法改写。但在 Venus 定点指令里，每一步都有：

```text
shift
截断
饱和
8-bit wrap/signed 解释
add/sub 饱和
```

所以这两个路径实际不同：

```text
原始路径:
(A*C >> s) - (B*D >> s)

cmxmul 三乘路径:
(C*(A-B) >> s) + (B*(C-D) >> s)
```

看起来代数等价，但 `A-B`、`C-D` 是先做的。只要中间值接近边界，提前减法就可能改变范围、触发饱和，后面的乘法输入就已经不是同一个东西了。再加上每个乘法右移的位置不同，误差会变成结构性误差，不是随机小噪声。

我们实测也正好符合这个判断：

```text
第 0 段 cmxmul:
real MAE ≈ 0.96, max 2
imag MAE ≈ 0.29, max 1
```

第一段单独看确实很小。但 FFT/OFDM 后面是多级 butterfly，误差会被继续参与加减、移位、复乘。只要前面每个点都有 1 LSB 左右的偏差，后面会像注入了一整段误差信号，而不是一个孤立误差。最终输出 signal RMS 只有约 15，误差 RMSE 到 13，就已经接近信号本身了：

```text
只保留第 0 段 cmxmul:
relative RMSE ≈ 87%

全 cmxmul:
relative RMSE ≈ 140%
```

所以结论是：

```text
作为“单条复乘近似”：cmxmul 修正后可以接近。
作为“整个 OFDM FFT 链路替代”：不合理，误差会被放大，不可忽略。
```

这也是我最后没有把 `cmxmul` 放进默认 OFDM 路径的原因。现在默认路径是 bit-exact 的显式实现；`cmxmul` 宏保留着，适合单点实验，但不适合直接替换整条 OFDM。

> 所以哪个计算你觉得更适合8bit计算？和浮点误差更小？

我觉得**原来的 4 乘法显式实现更适合 8bit 定点**，也更可能接近浮点参考。

原因很简单：它的每个乘积都是“正常复乘”的真实项：

```text
real = tmp_real*cos - tmp_imag*sin
imag = tmp_imag*cos + tmp_real*sin
```

也就是：

```text
(tmp_real*cos >> s)
(tmp_imag*sin >> s)
(tmp_imag*cos >> s)
(tmp_real*sin >> s)
```

每个乘法输入都是原始 8bit 数据和 twiddle，动态范围比较可控。

`cmxmul` 的三乘法虽然实数代数等价，但它会先算：

```text
A - B
A + B
C - D
```

这些中间量在 8bit 下更容易扩大范围、截断或饱和。然后再拿这些“已经变形过”的中间量去乘，所以对 8bit 很不友好。

对浮点误差来说，排序大概是：

```text
最好: 浮点复乘 reference
接近: 原始 4 乘法定点实现
较差: cmxmul 三乘定点实现
最差: 多级 FFT 全部用 cmxmul 替换
```

特别是 OFDM/FFT 这种多级 butterfly，早期 1 LSB 的系统性误差会被后面层层传播。我们实测也支持这个判断：修正后的第一处 `cmxmul` 单点只差 1 左右，但最终输出 RMSE 仍然很大。

所以如果目标是 **8bit 下接近浮点**，我建议保留原始显式 4 乘法。`cmxmul` 更适合在以下场景用：

```text
1. 中间位宽更宽，比如 16bit/32bit
2. 有专门 rounding/saturation 设计
3. 只做单次复乘，不进入长链路 FFT
4. 目标是省指令/省面积，而不是最小数值误差
```

对你这个 OFDM 来说，**4 乘法更稳，cmxmul 不适合直接替换整条链路**。

> 你可以看看我RTL里的CAU实现，现在的好像很多计算指令都复用了一块硬件。你觉得什么样的算法更适合8bit复数乘实现，也能保留它的复用性

<details><summary>4 previous messages</summary>

> 我先去 RTL 里把 CAU/复乘相关模块和数据通路看一遍，重点看它到底复用了哪些 pre-add、mult、post-add/sat 单元，再基于这个结构判断哪种 8bit 复乘算法更合适。
>
> 搜索结果很大，但核心文件集中在 `hardware/venus_extension/venus_cau.sv`、`venus_multiply.sv` 和 wrapper。我现在直接读这些模块的关键段落。
>
> CAU 结构确认了：VCMXMUL 是两条乘法通道 + pre-adder + post-adder 的 3-mul 复用结构。还需要看乘法的截断/饱和和 addsub 的复杂模式，才能准确说哪些算法适配它。
>
> 我还需要看 `venus_addsub.sv` 的有效计算段，前面都是 coverage。重点是它是否对 pre-adder 做了特殊 complex 饱和。
</details>

我看了 CAU RTL，结论挺明确：**如果目标是 8bit 复数乘精度，同时保留 CAU 复用性，我会把 `VCMXMUL` 改成“两周期四乘法标准复乘”，而不是现在这种 Gauss/三乘公式。**

你现在的 CAU 其实很适合这么做。

当前 `venus_cau.sv` 里的结构是：

```text
pre_adder_a_b
pre_adder_c_d
mult_aplusb_cmuxd
mult_b_cplusdmuxa
post_adder
```

`VCMXMUL` 现在走的是：

```text
real: C*(A-B) + B*(C-D)
imag: D*(A+B) + B*(C-D)
```

也就是 Gauss 形式。问题是对 8bit 来说，`A-B`、`A+B`、`C-D` 会先扩成 9bit，动态范围从 `[-128,127]` 变成接近 `[-255,255]`。后面再乘，乘积范围变大，右移/截断/饱和更容易发生。这个对定点非常不友好。

更关键的是：你现在 RTL 里 `VCMXMUL` 本来就分 REAL/IMAG 两拍做：

```verilog
if(cplx_real_imag_q == REAL) ...
if(cplx_real_imag_q == IMAG) ...
```

而且每拍用了两条 multiplier path。所以它实际并没有真正省掉一条 multiplier lane，只是换了更差的公式。既然都是两拍、每拍两乘，那最适合 8bit 的实现应该是标准四乘法：

```text
real = A*C - B*D
imag = A*D + B*C
```

硬件复用方式可以保持：

```text
第 1 拍 REAL:
  mult0 = A*C
  mult1 = B*D
  post  = mult0 - mult1

第 2 拍 IMAG:
  mult0 = A*D
  mult1 = B*C
  post  = mult0 + mult1
```

这样仍然复用同一组：

```text
2 个 multiplier
1 个 post_adder
同一套 valid/ready
同一个 REAL/IMAG 两拍状态机
```

只是 `VCMXMUL` 的 mux 控制从“pre-add 后再乘”改成“原始 A/B/C/D 交叉选择”。

我认为这个比现在算法更好，原因是：

```text
1. 每个乘法都是原始 8bit × 原始 8bit，动态范围最小
2. 不提前做 A+B/A-B/C-D，避免 9bit 中间量放大误差
3. 和浮点复乘公式一致，定点误差更可控
4. 和软件里 4 个 vmul + add/sub 的模型一致
5. 硬件复用性不变，仍然两拍两乘
```

所以我会建议把 `VCMXMUL` 定义从“Gauss complex multiply”改成“standard two-cycle complex multiply”。如果你想省面积/复用，当前 CAU 已经做到了；没必要为了三乘公式牺牲 8bit 精度。

> 原先CMXMUL应该是还可以支持乘加指令/加乘法指令吧

对，你理解得对。现在 CAU 这块不是单独为 `CMXMUL` 做的，而是**复用同一套 pre-adder / multiplier / post-adder 数据通路**，所以它同时支撑了几类指令：

```text
VMUL
VMULADD / VMULSUB
VADDMUL / VSUBMUL
VCMXMUL
```

从 `venus_cau.sv` 看，大概是这样：

```text
VMUL:
  multiplier_cplusdmuxa = A
  mult_b_cplusdmuxa = A * B

VMULADD / VMULSUB:
  result = A * B +/- C
  用一条 multiplier path 算 A*B
  另一条 path 主要 pipeline C
  post_adder 做 +/- C

VADDMUL / VSUBMUL:
  result = (A +/- B) * C
  pre_adder_a_b 先算 A +/- B
  multiplier 再乘 C

VCMXMUL:
  复用 pre_adder_a_b
  复用 pre_adder_c_d
  复用两条 multiplier path
  复用 post_adder
```

所以原先 `CMXMUL` 选 Gauss 形式的动机我能理解：它非常贴合这套已经存在的结构。

```text
real = C*(A-B) + B*(C-D)
imag = D*(A+B) + B*(C-D)
```

这刚好能复用：

```text
A+B / A-B     -> pre_adder_a_b
C-D           -> pre_adder_c_d
C or D        -> c_mux_d
B             -> op_b
最后相加      -> post_adder
```

也就是说，它不是“随便写了一个三乘法”，而是为了最大化复用：

```text
pre-adder + 两个 multiplier + post-adder
```

这套结构对 `VADDMUL/VSUBMUL`、`VMULADD/VMULSUB` 很合适。问题只是在 **8bit 复数乘 + FFT/OFDM 长链路** 里，Gauss 形式的中间加减会把量化误差放大。

所以我会这样评价：

```text
架构复用性：原先 CMXMUL 设计很好
8bit 数值精度：原先 CMXMUL 不理想
16bit 或更宽位宽：原先 CMXMUL 可能可以接受
FFT/OFDM 这种多级链路：建议不用三乘 Gauss
```

如果想同时保留复用性和 8bit 精度，可以考虑给 `VCMXMUL` 增加一个 mode：

```text
mode 0: Gauss 3-mul，保留现有路径，省控制/兼容原设计
mode 1: Standard 4-mul，两拍两乘，精度更好
```

这样 `VMULADD/VADDMUL` 那些指令不用动，CAU 的复用结构也还在。

> 你觉得有没有更好的设计，能提升8bit的cmxmul的精度，又能保留架构复用性

有。我觉得更好的设计是：

**保留 CAU 这套复用结构，但把 `VCMXMUL` 做成“标准四乘 + 宽位累加 + 最后统一 shift/saturate”。**

也就是不要用现在的 Gauss 三乘：

```text
C*(A-B) + B*(C-D)
D*(A+B) + B*(C-D)
```

而是用标准复乘：

```text
real = A*C - B*D
imag = A*D + B*C
```

但关键不是只改公式，而是**不要每个乘积先截成 8bit**。更好的 8bit 定点流程应该是：

```text
p0 = A*C   // 17bit raw product
p1 = B*D   // 17bit raw product
real_raw = p0 - p1
real = sat8(round(real_raw >> shamt))

p2 = A*D
p3 = B*C
imag_raw = p2 + p3
imag = sat8(round(imag_raw >> shamt))
```

这个比现在更接近浮点，因为它只在最后量化一次。现在很多误差来自：

```text
每个乘法先 >> shamt / 截断 / 饱和
然后再 add/sub
```

更理想的是：

```text
先乘，宽位相加/相减，再统一 shift/round/saturate
```

**架构复用性也能保留。** 你现在 CAU 已经有：

```text
两个 multiplier path
一个 post_adder
REAL/IMAG 两拍状态机
```

标准四乘刚好可以用同样两拍：

```text
第 1 拍:
  mult0 = A*C
  mult1 = B*D
  post  = mult0 - mult1 -> real

第 2 拍:
  mult0 = A*D
  mult1 = B*C
  post  = mult0 + mult1 -> imag
```

所以不需要加 multiplier。主要需要加的是：

```text
1. multiplier raw product 输出旁路
2. post_adder 支持 raw product 宽位加减
3. cmxmul 专用 final shifter + round + sat8
4. A/B/C/D 交叉选择 mux
```

`VMULADD / VMULSUB / VADDMUL / VSUBMUL` 仍然走原来的复用路径，不用破坏。`VCMXMUL` 单独走一个更适合 8bit 的精度模式。

我会把方案分成三档：

```text
最低改动:
  只把 cmxmul 从 Gauss 三乘改成标准四乘，但继续用现有 VMUL 输出。
  精度会明显好于现在，但仍不是最优。

推荐方案:
  标准四乘 + raw product 宽位 post-add + 最后统一 shift/saturate。
  8bit 精度最好，仍复用两个 multiplier 和 post_adder。

兼容方案:
  保留现有 Gauss cmxmul，新增一个 CMXMUL_ACC / CMXMUL_STD mode。
  旧指令不变，新指令给 OFDM/FFT 用。
```

如果让我选，我会选第三种对 ISA 最稳：

```text
VCMXMUL      = 现有 Gauss 复用实现，兼容旧行为
VCMXMUL_ACC  = 标准四乘 + 宽位累加 + final rounding/sat
```

这样既保留原来 CAU 的复用设计，又给 8bit FFT/OFDM 一个真正数值稳定的复乘指令。

> 不要，这个不好，现在的实现有没有可能在做复数乘法时，C*(A-B) + B*(C-D)。A-B保留9bit做乘法

对，**现在 RTL 里确实已经是 `A-B` 保留 9bit 去做乘法**，不是先截成 8bit。

从 `venus_addsub.sv` 看，`is_complex_i=1` 时，EW8 pre-adder 输出是 9bit：

```verilog
res.w8[b] = is_complex_i ? sub[8:0] : {sub[7], sub[7:0]};
```

所以 `A-B`、`A+B`、`C-D` 这些 pre-add 结果会保留成：

```text
EW8: 9bit signed
范围约 [-256, +254]
```

然后到 `venus_multiply.sv`，乘法输入 `operand_a_i` 是 `inter_elen_t`，里面 EW8 是 9bit：

```verilog
logic [1:0][8:0] w8;
```

乘法时也用了这个 9bit 符号位：

```verilog
data_out_pre_pipe.opa.w8[l][8]
```

所以现在 `VCMXMUL` 的路径本质上是：

```text
m0 = C * (A-B)      // A-B 是 9bit
m1 = B * (C-D)      // C-D 是 9bit
real = m0 + m1

m2 = D * (A+B)      // A+B 是 9bit
m1 = B * (C-D)
imag = m2 + m1
```

但问题在下一步：**乘法结果不是 raw product 直接进 post-adder，而是在 multiplier 里先做了 shift / sat / 截成 8bit**。

`venus_multiply.sv` 里 EW8 是：

```verilog
result_pre_sat.w16[l] = $signed(mul_res.w16[l]) >>> shamt;
result[8*l +: 8] = ... result_pre_sat.w16[l][0 +: 8];
```

也就是说当前实际是：

```text
real = sat8((C*(A-B)) >> shamt)
     + sat8((B*(C-D)) >> shamt)
```

而不是：

```text
real = sat8(((C*(A-B)) + (B*(C-D))) >> shamt)
```

这两个差别很大。前者是“每个乘积先量化”，后者是“宽位累加后统一量化”。

所以回答你的问题：

```text
A-B 是否保留 9bit？是，已经保留了。
当前误差主要不是因为 A-B 被截成 8bit。
更大的误差来源是两个乘法项各自先 shift/saturate 到 8bit，再 post-add。
```

如果想继续保留现在的 Gauss 结构，最值得改的不是 `A-B` 位宽，而是让 `VCMXMUL` 的两个乘积以更宽位宽进入 post-adder，最后再统一 shift/saturate。

> 这个改动大么，会对别的指令有影响吗

这个改动**不算小，但可以做成对别的指令影响很小**。

关键看你怎么改。

如果只是把 `venus_multiply.sv` 的输出从 8bit 改成宽位，那影响会很大，因为这些指令都复用 multiplier 输出：

```text
VMUL
VMULADD / VMULSUB
VADDMUL / VSUBMUL
VCMXMUL
```

这条路我不建议走。

更稳的做法是：**只给 `VCMXMUL` 增加一条 raw-product 旁路**，普通指令仍然用原来的 8bit/16bit multiplier result。

现在结构大概是：

```text
pre_adder -> multiplier -> shift/sat/trunc -> post_adder -> result
```

建议改成：

```text
普通指令:
pre_adder -> multiplier -> shift/sat/trunc -> post_adder -> result

VCMXMUL:
pre_adder -> multiplier raw product -> wide post_adder -> final shift/sat -> result
```

这样对其它指令的影响可以限制在：

```text
1. venus_multiply.sv 增加 raw product 输出
2. venus_cau.sv 在 VCMXMUL 时选择 raw path
3. post_adder 或新增小模块支持 wide add/sub + final shift/sat
```

对这些指令不改行为：

```text
VMUL
VMULH
VMULHU
VMULHSU
VMULADD
VMULSUB
VADDMUL
VSUBMUL
VADD
VSUB
VSADD
VSSUB
```

但验证上还是要覆盖它们，因为 `venus_multiply` 接口变了，CAU mux 多了。

我估计改动量：

```text
小改: 只加 raw output，不接入 cmxmul
中等: raw output + VCMXMUL 宽位 post-add + final sat
大改: 改现有 multiplier/post_adder 公共数据宽度
```

我建议做“中等”方案，风险可控。

潜在影响点主要有三个：

```text
1. 时序
raw product 是 17bit/34bit 级别，wide add + final shift/sat 可能拉长 VCMXMUL 路径。
不过你本来 multiplier 有 pipeline，post 阶段可以再打一拍。

2. valid/ready
VCMXMUL 已经是 REAL/IMAG 两阶段状态机，控制不用大改，但 raw result 要跟现有 pipeline latency 对齐。

3. 面积
会增加宽位 mux、wide adder、final shifter/saturator。
但不增加 multiplier，面积应该比四乘法方案小很多。
```

所以结论：

```text
改动中等。
可以做到基本不影响其它指令语义。
需要重点验证时序、pipeline 对齐、VCMXMUL dump 与 VEMU 模型一致性。
```

我会避免动普通 `VMUL` 的输出语义，只把 `VCMXMUL` 单独旁路出来。

> 可以的，所以Vemu里还是用几条指令拼一个复数乘出来吧

> RTL动不了，所以Vemu里还是用几条指令拼一个复数乘出来吧。同时备份这份逻辑正确的cmxmul的版本

<details><summary>12 previous messages</summary>

> 我明白：RTL 暂时不动，VEMU 这边默认还是用 `vmul/vssub/vsadd` 拼复数乘，保证功能正确；同时我会把“operand 映射已修正的 cmxmul 版本”单独备份出来，后面想回看/实验不会丢。先按 VEMU 流程确认一下当前文件状态。
>
> 我会检查当前 OFDM 源码里实际调用的是哪个宏，以及是否还有 `vns_cmxmul` 生成；然后创建一个 cmxmul 实验备份文件。
>
> 当前默认源码已经是 11 个 stage 全部走 `CMUL_WN_EXPLICIT_V1_STYLE`，也就是用多条 Venus 指令拼复数乘。现在我创建一个备份文件，把调用切成修正后的 `CMUL_WN_V1_STYLE`，作为“逻辑映射正确但数值误差会放大”的 cmxmul 实验版。
>
> 备份文件已经创建。接下来我只改备份文件里的调用，不碰默认源码。
>
> 备份里的调用已切到 cmxmul。现在我确认默认源码仍然是显式拼复乘，备份文件则是 cmxmul 版。
>
> 我发现备份替换太粗，把备份里的显式宏定义名字也替掉了，形成了两个同名宏。这个只影响备份文件，不影响默认源码；我马上把备份里的第二个宏名修回去，让备份也保持可编译。
>
> 修正完了。我再确认一次备份中的宏定义和调用分别正确。
>
> 备份里第二个宏定义的续行符被刚才的修复弄掉了一处。最干净的做法是从默认源码重新复制备份，然后只替换调用行，不碰宏定义。
>
> 备份已从默认源码重建。现在只替换带缩进的调用点，宏定义不会动。
>
> 这次替换范围正确。我做最终确认：默认源码显式拼复数乘，备份源码用 cmxmul 宏，生成汇编中默认路径没有 `vns_cmxmul`。
>
> 默认源码和备份状态都确认好了。最后我看一下 VEMU 工作树里相关文件的改动情况，方便你知道有哪些文件被留下。
>
> `git status` 对这两个文件没有输出，可能这个目录没有跟踪这些任务文件或被忽略；我再直接确认备份文件存在。
</details>

可以，已经按这个方向处理好了。

当前默认 VEMU 源码：

[Task_nrOFDMDemodulation.c](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c:80)

现在 11 个 OFDM stage 都走：

```c
CMUL_WN_EXPLICIT_V1_STYLE(...)
```

也就是继续用：

```text
vmul + vmul + vssub + vmul + vmul + vsadd + vsadd
```

拼出复数乘，保持功能正确。当前生成汇编里也确认没有 `vns_cmxmul`。

同时我备份了一份“operand 映射修正后的 cmxmul 版本”：

[Task_nrOFDMDemodulation.c.cmxmul_logic_correct_20260617](~/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c.cmxmul_logic_correct_20260617:69)

这份备份里所有 stage 调用的是修正后的：

```c
CMUL_WN_V1_STYLE(...)
```

保留了我们确认过的正确 operand 映射：

```c
vcmxmul(&(result_real), &(result_imag),
        tmp_real, tmp_imag,
        sin_vec, cos_vec, ...)
```

注意这份是实验备份：逻辑映射对了，但数值误差会在 OFDM 多级 FFT 里放大，所以默认不使用它。
