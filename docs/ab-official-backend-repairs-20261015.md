# A/B 冻结路线：本轮修复与准入边界

用户已要求先完成 A/B，文献和 Open Targets 的新构建及请求已停止。
本轮处理实际冻结路线，而不是把历史 120 个候选或通用同名节点当作当前启用清单。

| 路线 | 实际节点 | 方法与输入边界 |
| --- | --- | --- |
| A | twosamplemr-v432-a/twosamplemr_v432_a_exploratory | 官方 TwoSampleMR 0.7.11、R 4.6.1；固定 seed 432202610、1000 bootstrap；已合格的 X01→M06 IV |
| B 输入 | frozen-b-project/frozen_b_legacy_intake | 19 个固定来源；不推断临床分组、不重新归一化 |
| B 设计与拟合 | bulk-limma-normalized/bulk_normalized_design、bulk_normalized_limma | 官方 limma 3.68.5、R/stats 4.6.1、statmod 1.5.2；原始 RMA log2，非 counts/voom |
| B 家族 | frozen-b-project/frozen_b_legacy_family | 三个预定模型各保留完整家族；只接收官方调整结果，不自行重算 |
| 共用输入 | core/file_reference | 内容身份与实际端口绑定；不是统计方法 |

旧 daemon 的确执行过 A 的 39 IV 以及 B 的三个 23,786 基因模型，不能再说它们从未运行。
这些是已见的 LEGACY_EXPLORATORY 结果；不能转为独立验证，不能用旧执行证明新修复已经部署。

## 已复现的缺陷及修复

- A 原脚本在验证完成前打开输出日志，能截断别名输入或旧日志；末端失败还会留下六表、RDS、日志。
  当前候选改为输入输出预检、私有暂存、独占发布与自有文件回滚，保留方法调用和随机序列。
- B 原 LIMMA 入口回滚直接删除已发布路径，故障注入证实会误删外部替换文件。
  DESIGN/LIMMA 候选改为核对 device/inode/uid，只回滚仍属于该次发布的文件。
- B 家族原来在 Python 自写 BH/BY。候选改为 R/stats 4.6.1 的 `stats::p.adjust`，
  在完整结果行序上分别执行 BH/BY；非估计原始 P 仍是 NA，仅调整向量取 1。
  Python 家族只验证、传递实际 q 列及其来源回执；旧生产者缺列或缺回执就拒绝，不回退自写算法。
- Python 输入/家族端点的普通发布故障也补上自有硬链接回滚，不删除已被替换的外部 inode。

官方调整参数 `n` 不小于完整输入长度；不能通过删失败行或拆批改变家族。
见 [R 官方定义](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)。
节点内新增 q 列不自动获得更大家族的资格；冻结家族仍核对原模型、全行数、身份与实际来源。
一个主要模型、两个预定敏感性模型分别处理，不事后合并或替换其分母。

## 证据，不混用等级

| 内容 | 封存会话 | 状态 |
| --- | --- | --- |
| A 三类旧 I/O 反例 | bf7c68c3d99a4f7c8eef4c94a60cfa6f | 已实际复现，非修复通过 |
| B 旧回滚误删 | 6eb5e78b95fd4969a88f15732536eb0b | 已实际复现，非修复通过 |
| A 最终 22 个 I/O 案例 | 8590c2ae114e438abb065cf2b5c3e6b8 | 含非抛错替换、同 inode 内容改写、暂存目录/日志替换；限定窗口通过 |
| A 最终官方方法及九端口 | 1f312ea09fab4cda915504195d289d63 | 两个正例、七个拒绝；官方完整 RDS、六 TSV、日志和来源 JSON 回读 |
| A 最终隔离 DAG | 4df28f3370674c25844f8bc692c13726 | 两张正图、一张失败图；每图六节点五边，非当前 daemon 资格 |
| B 最终 18 个 I/O 案例 | 7aae6ab1be8b49ceb7d154016b716a30 | 含同 inode 内容改写；限定故障窗口通过 |
| B 三模型、25 基因独立官方数值块及 RDS/q 回读 | 186a1ed980cd48f6908f0e7201420f7f | host 实际通过，非真实队列或当前 daemon 资格 |
| B 最终三模型隔离 DAG 及上游失败 | 7b67c1da0b9b47c4bf72e893d8e4eba9 | 每张正图七节点十一边；完整表、官方 q、RDS 选定组件；上游失败阻断下游 |
| 家族机械传输旧反例和最终 12 项 toy 测试 | ac64b2c63d254fe296e463f35553cfb9 | 三个旧反例测试失败、修复十二项通过；该项本身不运行 R 或 DAG |

细节及封存 SHA 分别见 [A 修复与隔离 DAG](frozen-a-io-current-dag-20261015.md) 和
[B 修复与隔离 DAG](normalized-b-io-official-adjustment-20261015.md)。
新的完整 frozen intake/family 正向生产种类 DAG、精确版本发布及当前 daemon 准入仍单列，
不因上述局部证明就将整个 A/B 标成完成。
普通回滚不等于断电恢复或 crash-atomic 事务；不能声称防住不合作进程对每一步文件操作的竞态。
失败诊断日志可以保留，但失败不能发布为成功科研结果。

## 当前不能宣称已经生产准入

运行服务的三个 A/B 插件仍是 mutable path；runtime 目录也是工作区符号链接。
注册表存在、磁盘文件哈希与已加载到内存的脚本身份不是同一证据。
须将三套插件锁定同一已证明的完整 Git revision，再验证实际加载与运行，不能只升级其中一套。
操作者已明确告知研究任务仍在运行、暂不重启；本轮不重启或热装生产。

A 上游原始 GWAS QC、PLINK 1.90b7.2 `--clump`/LD paircheck、TwoSampleMR 0.7.11
`format_data`/`harmonise_data(action=2)` 有冻结的官方实际执行证据，但不在当前六节点 MR 图中重跑。
不能用泛型 PLINK2 矩阵加自写 greedy 或 TwoSampleMR 0.7.9 的适配器替代这一固定上游合同。
当前预选 IV 数值适配器也不是“全 A 原始数据资格生产流程已在当前 DAG 验收”的证书。

本轮未修改冻结设计、276/288/696 家族、查看史或科学签名。技术修复不是 G0 PASS。
空间 B-S 保持 CONDITIONAL_NOT_READY，GS01 保持 OPEN。
