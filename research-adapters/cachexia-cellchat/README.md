# CellChat 受控研究适配器

此路线直接调用固定官方 CellChat，不修改统计实现，不替换生产 `cellchat_inference`。
镜像固定为 manifest 中完整 digest；运行时无网络、一个 worker、一个 CPU、2 GiB。
这是小规模技术验证预算，不是全研究规模的资源保证。

## 方法与边界

官方源码：`jinworks/CellChat@75253cd0c9e68410e6e721a6d3a0419a1d7e358f`；
快速 Wilcoxon 后端：`immunogenomics/presto@b5df6ee6097eb62522f2e557aa93ac21bab2d05f`。
内嵌 human/mouse DB 随镜像固定。流程为 create/subset、官方过表达筛选、
triMean computeCommunProb、min.cells=10 过滤、pathway/aggregate/centrality。
所有其他调用约定见脚本和完整官方对象；不包含投影、空间、合并或可视化。

CellChat 的置换单位是**细胞标签**，不是独立供者。这条路线只生成组织内
候选通讯连接，不授予供者级差异推断、循环因子到达、跨器官运输、因果结论或 G0。
官方经验 P 值可能为 0；原样保留，不改成其他置换检验的 add-one 约定。
`nboot` 的 10–500 技术范围不证明研究检验精度，不可据此放行正式显著性结论。

## 输入合同

端口 0：完整不可变 H5AD，X 为 CSR、CSC 或标准二维 dense，obs/var `_index`
属性指定轴名，支持自定义 index dataset。分类缺失码/越界、重复轴、非有限/负表达、
无效稀疏结构、重复坐标、零库细胞及少于 10 细胞的群均拒绝。
obs 必须具有冻结的 group、donor、tissue 列；供者记录并非独立性认证。

端口 1：20 个键的 JSON，完整实例由 `scripts/cachexia_cellchat_cases.py` 提供：
`schema_version,input0_sha256,scale,species,db_scope,seed,nboot,group_column,donor_column,`
`tissue_column,expected_genes,expected_cells,expected_groups,expected_donors,expected_tissue,`
`scope,null_unit,family_id,test_id,input_origin`。
所有键必填，重复/未知键拒绝。不得用节点默认值补研究规则。

`scale` 仅接受 raw_counts 或 log1p_cp10k，禁止 auto。raw 必须为非负整数，
在完整库上按 log1p(count/library_size*10000) 归一化；log 值不再归一化。
哈希/声明不自动证明来源或尺度正确，真实输入仍须外部资格审核。
scope/null_unit 固定为 within_tissue_candidate_only /
official_cell_labels_not_donor_inference。input_origin 仅允许合成技术数据或
LEGACY_SEEN 历史复现；此适配器无权自行批准新研究输入。

## 八个输出

| 端口 | 文件 | 含义 |
|---|---|---|
| 0 | values.tsv | 所有官方入选 LR 的 source×target 概率/P 值，含零值与不显著项，行身份固定 |
| 1 | cellchat.rds | 完整官方 S4 对象、全部 slots/属性/DB/net/netP/参数；运行时间也保留 |
| 2 | audit.json | 输入输出 SHA256、完整合同、技术状态及科学边界 |
| 3 | cellchat.log | 技术通过或具体阻断原因 |
| 4 | cells.tsv | 完整 cell/group/donor/tissue/原始位置 |
| 5 | genes.tsv | 完整 gene/原始位置，不偷偷删原始基因 |
| 6 | state.rds | RNG 前后状态、完整警告与合同 |
| 7 | family.tsv | 完整所选 DB×source×target；未入官方估计的组合显式 NOT_ESTIMATED_OFFICIAL_SELECTION |

family.tsv 是候选宇宙账本，不宣称未估计项有有效 P 值，也不是自动完成研究家族校正。
失败只保留 audit/log，清除本次分析产物，不回退其他算法。
所有输出须按声明端口验收，不允许烟测人为补第九个端口。

## 复核

`scripts/prove_cachexia_cellchat.py` 使用实际六节点 DAG，输出经 reader/typed SQL/sink
物理落盘。独立入口 `study_plugins/tests/cellchat_reference.R` 不导入适配器，
从原始合成数值重建表达矩阵，核对官方函数体/formals 和 human/mouse 全 DB，
比较完整 S4/RNG/警告及结果表。仅 `options$run.time` 属于执行时长而非数值状态；
双方完整对象和时长仍保留，其他 slots/属性要求完全一致。

历史生产 wrapper 的方法调用与接口缺口分开记录；不能把组织门槛缺失称作
官方 CellChat 算法错误，也不能把这条限定路线外推为旧 wrapper 或全 API 的认证。
