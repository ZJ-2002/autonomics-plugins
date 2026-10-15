# Normalized B：输出保全、官方校正与当前 DAG 技术证明

日期：2026-10-15。结论：`ACCEPTED_SCOPED_SYN_NORMALIZED_DESIGN_LIMMA_DAGS`，
不是完整 B 研究、完整 family DAG、生产部署或 G0 放行。
机器可读索引：`evidence/normalized-b-io-official-adjustment-20261015.json`。
下述档案标识及 SHA256 用于核查私有技术档案；本文不发布档案内容或研究数据。

## 1. 最终源码身份

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| `plugins/bulk-limma-normalized/scripts/run-design.R` | 19849 | `ed9ab1fd7b4c5f4533a7fac14d50ded9c829a840e849d974486945534648d707` |
| `plugins/bulk-limma-normalized/scripts/run-limma.R` | 21594 | `a300208080b1cf6c8d3361fe4f0dbea50977a45f7e76fed00bfe49dc7def738c` |
| `plugins/bulk-limma-normalized/manifest.toml` | — | `d643744bb9c96c31f3e0f86b8782ff61a66ec4281ca3b0c45bbc041dbcda09f2` |

最终 DAG 使用这些 manifest / script 字节的独立副本，而不是读取可变默认插件。
内嵌数值部分（`entry_main` 前的原始字节）保持不变：DESIGN 16694 字节，
SHA256 `5f8300f0078ee45531efb16fd8ecad726ba52a6a24c2824b0f8418979d504d2e`；
LIMMA 16693 字节，SHA256
`7723131e15c4aeb64a8b58ee97756028cf191ad3bdcbb85e22ab88da50d3b1cc`。
传输尾段的官方校正和发布安全变化分别由下列完整数值及故障注入证明覆盖。

## 2. 实际缺陷与修复

此前回滚仅按输出路径删除，可能删除外来替换文件；第一轮修复仅比较
device/inode/owner，仍无法识别同 inode 的内容改写。最终修复在第一个
输出硬链接之前固定整个私有 bundle 的 inode/owner 和 SHA256；逐端口检查、
最终完整集合检查和失败回滚均比较这些预期值。回滚只删除仍与自身原始
身份和内容一致的输出，保留外来替换及同 inode 已被改写的文件。
已有文件、悬空符号链接和输入别名仍拒绝覆盖；输入摘要在每个控制前后相同。

这不是跨进程事务或崩溃原子性证明，也不保证最后一次检查之后的一切敌对竞态。
不能据此宣称断点恢复、持久缓存复用或撤证机制已经通过。

### 最终 18 项真实 R 入口 I/O 控制

该测试仅用 stub 方法隔离真实 `entry_main` 的发布逻辑，不把 stub 结果当作
官方 limma 数值证明。DESIGN 和 LIMMA 各测试正常发布、已有输出、悬空链接、
输入作为输出，共 8 项；另有 LIMMA 的外来替换后晚失败、自有输出后晚失败，
以及两个入口各自的链接后外来替换，共 4 项。最后 6 项保持 inode 不变：

- DESIGN 和 LIMMA 各自的早端口改写、最终端口改写（4 项）；
- LIMMA 最后一次链接时改写早端口（1 项）；
- LIMMA 改写早端口后触发晚失败，检查回滚不得删除改写内容（1 项）。

正常发布返回 0，其余 16 项返回 2；要求保留的内容和全部输入摘要均正确。
档案 `7aae6ab1be8b49ceb7d154016b716a30`：`CLEANED`、worker 0，
95 个文件完整成员、大小、摘要已重核；manifest SHA256
`d794d8c4bfc78badc88294913ed644b01b44c67fc6025da4cc561c976beb6278`。
证据入口：`permanent/normalized-b-publication-repaired/verification.json`。
此档案使用 runtime `f32991937c824d56ead0ecee66979f20030a55410e68c56c1c57ff37880cc1fa`，
未启动容器；不能将它的 runtime 外推为最终容器运行资格。

### 先失败后修复的记录限定

六项同 inode 反例首先在旧入口上复现：档案
`820a0b77215b42788deb750f4d5353fc`，35 文件，seal
`c442763dbf343e5675a317d5cdcc1ae7b8c6eb441489cec5e0534716dc7f7366`。
前五项错误返回成功，晚失败项错误删除改写文件；逐项保存
`expected_regression_assertion` 和改写前后相同 inode 身份。
该版 driver 的总字段 `baseline_regression_reproduced` 仅判断
`phase == 'baseline'`，因此在 `identity-baseline` 中错误记录为 false。
不能引用此总字段作为反例成功或失败的裁决；复现依据是上述六项实际结果。
源码已改为 `endswith('baseline')`，旧封存未改写。

## 3. 官方计算路径及固定参照

实测包版本为 R 4.6.1、limma 3.68.5、statmod 1.5.2、stats 4.6.1。
拟合仍为官方 `limma::lmFit` / `limma::eBayes(trend=TRUE, robust=TRUE)`，
仅适用此合同的 normalized log2 输入，不接受 counts，也不改走 voom 或原生 OLS。

节点尾段在完整结果表上直接调用 `stats::p.adjust`，分别计算 BH 和 BY，
`n = nrow(results)`。本次每模型 25 行：24 个 ESTIMATED、1 个常量行。
常量行的原始 P 和 family P 保持 `NA`，只在校正输入向量中以 1 占位。
结果新增 `q_BH`、`q_BY`，并写入实际 `family_adjustment` 软件与分母回执。
RDS 保持官方拟合对象，不冒称其中新增了 q 对象。

独立固定参照是此前已经封存的三模型 25 基因、8 个 SYN 单位测试：
`186a1ed980cd48f6908f0e7201420f7f`，61 文件，seal
`efded200ef0755472fda92543d4ce48095799e78828560fa66d54b57968f73cc`。
本轮对完整参照重新核对成员和摘要，不重生或改写 golden。此前独立 R 进程
运行原冻结数值块，保存 beta/SE/df/CI/raw P 和全部 BH/BY 向量；本轮当前 DAG
对照这些固定向量，同时比较原节点全部 25 列与完整审核回执。
既往宿主 toy 中独立 OLS 仅核对系数，不构成独立经验贝叶斯先验正确性证明。

## 4. 最终实际当前引擎 DAG

执行档案：`7b67c1da0b9b47c4bf72e893d8e4eba9`；71 文件完整重核，
seal `74e5d3882983b5f07984a488d74fa0cfaf8ce9fcf776a81d50d9260863b7cb89`；
状态 `CLEANED`、worker 0。入口：
`permanent/normalized-b-current-dag/VERIFICATION.json`。

精确复用引擎 `4ceefbd821baab8deebb070645a2fb8b1fa8e1ba` 的已封存 runner，
可执行 SHA256 `bbc1a387b508ba05c50e79eb95b3dc15f87cf274a6e2c3983bcd320246339481`，
不重新构建。使用强受管 runtime
`985b77dcaf5adf490b1ba5a523dec0aa66ceeac5897f2abfa7704c57a8987f65`，
实际 shim SHA256
`e422b7a14ad9681ce9a90ae57120a228bf59e336ad1fb0ce448dd76e78320c7d`。
私有已安装镜像的 manifest/config/全部 layer 身份实际核对；不拉取、不构建、
不重装。镜像：
`localhost/autonomics/frozen-b-normalized@sha256:723904dd46c9148d75716555e2f641604d98c22909bc333d5fac832f33ebffed`。
运行限制为单容器、1 CPU、1 GiB、禁网、只读根文件系统；不挂载真实研究数据。

| SYN 模型 | 实际节点/边 | 实际输入绑定/输出端口 | 全表/冻结向量最大绝对差 |
| --- | --- | --- | --- |
| primary | 7 / 11 | 11 / 4 | `2.4980018054066022e-15` |
| unadjusted | 7 / 11 | 11 / 4 | `1.2212453270876722e-15` |
| therapy_sensitivity | 7 / 11 | 11 / 4 | `9.992007221626409e-16` |

每图为五个 File reference → DESIGN → LIMMA，同时五个文件直连 LIMMA。
逐输入核对真实 staging 字节和端口边，逐输出核对声明端口、实际文件及 SHA256；
逐行保留顺序、ID、状态和缺失掩码。数值容差沿用 `rtol=1e-11, atol=1e-12`，
没有按通过情况放宽。第四图仅改变 SYN 配置的表达尺度为 raw counts：
DESIGN 明确以尺度合同错误退出 2，LIMMA 为 SKIP、未执行、无方法产物；诊断日志保留。

另一个实际容器重新读取三个 RDS，核对完整基因/可变基因 ID，以及
`coefficients`、`stdev.unscaled`、`sigma`、`df.residual`、`s2.prior`、
`df.prior`、`s2.post`、`df.total`、`t`、`p.value`、`Amean`、`cov.coefficients`
12 个拟合组件。此为所列组件对照，不是每个对象槽位或环境的全面等价证明。
所有 8 个容器 intent 的最终 `containers_remaining` 均为 0。
计算中生成的 VERIFICATION 将停止检查标记为待 reconcile；最终停止事实来自
同一不可变档案内的 `permanent/container-stoppage.json`，没有事后改写计算记录。

## 5. 历史证据与仍未覆盖范围

- 旧 12 项 I/O：`76c1cd99f76c47c785a77df814dc6795`；有历史价值，
  不替代当前 SHA 的 18 项控制。
- 宿主 toy `186a1ed980cd48f6908f0e7201420f7f` 是固定数值参照，
  不将其旧 wrapper 身份冒称本轮最终发布源码。
- 旧 DAG `5a1eeb7158b249449fbfd9aa13328abc` 使用旧 wrapper 与临时 runtime f329，
  仅保留历史；最终判断使用 `7b67c1da0b9b47c4bf72e893d8e4eba9`。
- 未运行真实 23786 基因/22 PDAC 供者研究，不授予真实来源资格、生物学独立性、
  统计设计科学签署或 G0；未启动完整 frozen family DAG。
- 未重启或热加载生产服务；不证明 resident daemon、生产版本同步、跨进程缓存、
  故障恢复、全局跨服务资源预算或全平台节点认证。
