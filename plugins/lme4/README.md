# lme4

通用长表混合模型插件，不自动决定研究公式、协变量、供者资格或科学放行。
固定镜像：
`ghcr.io/zj-2002/lme4-r@sha256:084479ed5409c42fbbcf630ce44f06a35d0e47ae22e40b185fcd453aeb09f88c`。
镜像实际包含 R 4.4.1、lme4 1.1-35.5、lmerTest 3.1-3、
broom.mixed 0.2.9.6、pbkrtest 0.5.3、data.table 1.16.2。
这是固定版本、限定范围的路线，不是最新版本全部 API 等价认证。
Dockerfile 是历史构建配方，包含可变安装源，不能代替上述已执行镜像的身份。

## 方法与参数

一个输入端口：长表 TSV，一行一个观测；样本/供者/切片关系由输入列和公式表达。
`formula` 必填，使用 lme4 公式；`family` 支持 gaussian/binomial/poisson。

- gaussian：`lmerTest::lmer`，`reml=true` 默认；Satterthwaite 默认或
  `ddf=kenward` 的 Kenward-Roger。显式向 tidy 传入 `ddf.method`，
  向 summary 传入 `ddf`；旧脚本的 tidy `ddf` 部分匹配本来有效，
  本次不能把它误报为新修复的自由度缺陷。
  Kenward-Roger 仅允许 REML；ML+KR 明确拒绝，不自动改用另一方法。
- binomial/poisson：官方 `glmer`、bobyqa、Wald z；
  `nagq=1` 默认 Laplace，0 是官方较快近似，>1 受官方单标量随机效应限制。
  `reml` 和 `ddf` 对 GLMM 不生效。
- `n_boot=0` 默认关闭；>0 对 LMM/GLMM 调用官方 `bootMer`，
  parametric、use.u=false、parallel=no、`seed=42` 默认。
  `boot_low/high` 是全部重复固定效应的 type=7 百分位数，不是 BCa、
  profile 区间或 bootstrap P 值。任何失败/非有限重复拒绝发布，
  不用 `na.rm` 缩小重复分母。少量重复的测试仅证明计算路径，
  不证明置信区间覆盖率或足够的科研 Monte Carlo 精度。
- `seed`、`n_boot`、`nagq` 必须是 [0, 2147483647] 的整数；
  布尔值只接受 true/false（大小写可变）。

## 三个输出端口

| 端口 | 文件 | 含义 |
|---|---|---|
| 0 | lme4_fixed_effects.tsv | broom.mixed 固定效应：effect/term/estimate/std.error/statistic/p.value/conf.low/conf.high；LMM 另含 df，启用 bootstrap 另含 boot_low/boot_high |
| 1 | lme4_random_effects.tsv | effect/group/term/estimate；ran_pars 的 **sdcor**：标准差与相关系数，**不是方差表** |
| 2 | lme4_model.txt | summary、输入/拟合观测数、参数、收敛/奇异状态、警告、是否发布估计及是否仅诊断 |

不提供拟合对象 RDS 端口。验证中的 RDS 是测试 harness 在 source 后回读派生的对象，
不是用户接口。公式环境、调用名称及 native 指针不能作为原始 merMod 逐字节等价依据。

## 失败、可靠性与兼容性变化

本轮先复现并修复四个反例：默认 NA 省略观测、秩亏静默丢系数、
非法 REML 布尔值变成 false、GLMM 的 n_boot 被忽略。
现在缺失/非有限模型值、秩亏、输入解析警告及非法参数均退出 2；
不默默改变观测或系数集合。供者编号的前导零保留；
NA/空字符串是缺失标记。由 fread 推断其他列类型，分类变量/参照水平
仍须由调用方明确编码及审核，不替研究者生成因果/纵向公式。

**新默认 `reliable_only=true`**：奇异或非收敛拟合退出 2，
保留模型诊断文本，不发布两张估计表。
显式 false 保留官方拟合供诊断，必须标记 `diagnostic_only: true`，
不能视为正式推断准入。判定是 optimizer 状态、lme4 消息、捕获的拟合警告与
官方 isSingular；boundary(singular) 消息不单独计为非收敛。
奇异意味着协方差边界，**不意味着每个随机效应的方差为零或生物学无变异**。

三端口拒绝覆盖既有文件；单文件先写临时文件再无覆盖链接发布。
同进程后续发布失败回滚本次估计表，不保证 kill -9 后三文件事务原子性，
也不证明 daemon 缓存、跨进程断点恢复或全局资源预算。
新 manifest/脚本需重新加载并独立验收；没有修改当前生产部署或冻结研究配置。

## 验证层次

`Rscript tests/test_lme4_fit.R` 是自洽回归/失败合同测试，不是独立参考。
另有 2026-10-11 验证包：四个真实 CRAN 作者源码重新安装（lme4 C++ 重编译），
在单独脚本/进程对照固定镜像，逐项比较输出表、拟合组件、观测/系数/分组轴、
bootstrap 全重复和 P 值对数。参考与待测共享固定底层依赖，
不宣称完全独立数值算法、跨平台精度或统计校准已证明。

官方源码 lmList.R:448-460 在构建时从 nlme 复制函数，导致四个
lmList4/gsummary 函数在旧二进制与新源码安装中不同。
它们不是本节点暴露的方法；完整 namespace 等价不成立，不能隐藏此差异。
节点限定为经测试的 lmer/glmer merMod 路线。

文档依据：[lmer](https://lme4.github.io/lme4/reference/lmer.html)、
[glmer](https://lme4.github.io/lme4/reference/glmer.html)、
[bootMer](https://lme4.github.io/lme4/reference/bootMer.html)、
[isSingular](https://lme4.github.io/lme4/reference/isSingular.html)。
版本语义以封存的 1.1-35.5 等作者源码为准，在线文档可能更新。

限定计算验证不证明 B-T 数据资格、信号×时间方案合同、
空间供者结构合格或 G0 科学签署。
