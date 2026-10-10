# CellTypist：冻结模型的技术注释路线

节点 `cachexia_h5ad_celltypist` 调用官方 CellTypist 1.7.1，不重写分类算法。
固定镜像和真实包版本见 manifest / `VERSIONS`；官方源码固定于
`fe357564a6625d3b1732a022fd39f18e55696e80`。既有节点向
`AnnotationResult.to_adata` 传入不存在的 `overwrite` 参数，本路线使用真实声明
参数，并将全部分类决策、概率、标签和官方置信分口径保留。

## 输入与冻结口径

三个 File 输入依次为 H5AD、官方原始模型 pickle、JSON 合同。模型仅接受官方
Pan Immune v2 `Immune_All_Low.pkl` / `Immune_All_High.pkl` 的已核对 SHA256。
读取 pickle **之前**核验身份；任意其他 pickle、转换/训练/裁剪后的模型不接受。
实际模型文件和官方 JSON 发布索引必须作为研究资源另行冻结，不能只固定文件名。

合同 22 个键见代码 `KEYS`，无节点默认方法参数。固定完整细胞、基因、模型类别、
参与预测基因的有序轴，输入内容哈希，人类符号命名空间，X 或明确 layer，
`log1p_cp10000_all_genes`，预测 mode / p_thres，投票开关、冻结 cluster 列、
min_prop、confidence_by、seed、技术 scope 和非候选结果驱动的 annotation_basis。
所有细胞检查数值、范围和反变换总量；不靠官方只看前 1000 个细胞的启发式，
也不将部分库的官方警告误认为有效的正式输入。

不做归一化、raw fallback、自动 cluster、跨物种/Entrez/Ensembl 映射、模型选择。
majority voting 必须已有完整冻结的字符串 cluster 列且细胞数 >50；官方会对
<=50 跳过投票，本路线直接阻断，避免“请求了投票但没有做”的静默改变。
模型重叠范围明确冻结，不发明“足够重叠”的通用科学阈值或组织适用资格。

## 输出

0. `result.parquet`：完整 cell×model-class 决策分和独立 sigmoid 概率；逐行附原始
   predicted label、over-cluster、majority label、conf_score、其来源和 test_id。
1. `output.h5ad`：原始 X / raw / layers / obs / var / embeddings / graphs 不变，
   仅新增 `cachexia_celltypist_` 名空间的官方标签、conf_score、完整矩阵和合同。
2. `audit.json`：版本、请求和输入/输出身份、模型重叠、类别、警告和技术状态。
3. `celltypist.log`：实际方法日志。
4. `genes.tsv`：完整输入基因轴及是否参与官方模型预测，不删未匹配基因。
5. `request_ledger.tsv`：单个冻结请求的技术状态；失败时保留可恢复的 test_id。

概率是官方逐类 sigmoid，不是 softmax、不保证每行和为 1，也不是已校准的科学
可信度。confidence_by 精确使用官方 `to_adata` 定义；majority label 不在模型
类别中时，官方使用该行最大概率，不能冒称该组合标签的后验概率。

官方 1.7.1 的 `prob match` 在全部未分配时会将 `Unassigned` 截断为 `U`
（固定长度 NumPy 字符串数组），原始输出虽与官方包相同，却不符合官方文档定义。
本路线逐行用真实决策分的 argmax（best match）或严格 `probability > p_thres`
（prob match）核查官方标签；不符合定义时阻断并在审计保存原标签/应有标签和
细胞 ID，**不静默重写、不认证官方 bug**。概率饱和时 best match 以决策分而非
概率的并列值决定类别。该上游缺陷未被我们改写；相应输入域未获可运行认证。

## 验收边界

真实完整官方模型用于技术合成矩阵；完整源码 namespace 对账、完整独立官方重算、
实际 materializing DAG 和明确阻断反例分别出证。不是实际组织准确性验证、供者级
差异分析或科学 G0。候选 gene 上调不授予注释决定权；本节点也不能证明上游没有
以查看过的候选结果挑 cluster。正式使用还需独立科学审核输入、模型和 annotation
freeze。未修改生产插件配置或 daemon；默认存储 ENOSPC、全局预算、持久恢复和
正式全方案可用性均不因隔离容器运行而关闭。
