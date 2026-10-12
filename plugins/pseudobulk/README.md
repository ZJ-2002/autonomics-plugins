# pseudobulk

单细胞 h5ad → 供者×细胞类型假体块计数。补齐主计划 §15.3 的缺口：
差异分析的统计单位是**供者**不是细胞；引擎原 registry 无 pseudobulk
聚合工厂。2026-10-04 增补 `h5ad_export_matrix`：X 层长表导出（引擎
原生 h5ad 工厂只有 obs 层，X 无导出路径的补位）。

## BREAKING CHANGE（2026-10-05，审计 F07）

`pseudobulk_counts` 输出表头与校验口径变更，`schema` 参数默认 `deseq2`：

| | `schema="deseq2"`（新默认） | `schema="legacy"`（旧口径） |
|---|---|---|
| counts 首列 | `gene_id` | `gene` |
| samples 首列 | `sample_id` | `pseudobulk_id` |
| samples 条件列 | 含 `condition`（取自 `condition_column` 参数） | 无 |
| 非整数矩阵 | **退出 2**（`allow_non_integer=true` 才放行 + WARN） | **同样默认退出 2**（须显式 `allow_non_integer=true`） |

旧 DAG 若依赖旧表头，须显式传 `schema="legacy"`；下游 DESeq2/limma-voom
节点按 deseq2 表头直读（首列作 row.names / rownames）。

## 节点

| kind | 输入 | 输出 |
|---|---|---|
| `pseudobulk_counts` | h5ad（AnnData） | `pseudobulk_counts.tsv`（基因 × `<sample>__<celltype>`）、`pseudobulk_samples.tsv`（含 `n_cells`；deseq2 另含 `condition`）、log |
| `h5ad_export_matrix` | h5ad（任意来源） | `x_matrix.long.parquet`（cell_id/gene/value）、`obs.tsv`、`var.tsv`、log |

参数：`pseudobulk_counts` 的 `sample_col`、`celltype_col`（必填），
`min_cells`（默认 10），`layer`（可选，默认 `.X`），`schema`
（默认 `deseq2`），`allow_non_integer`（默认 false），`condition_column`
（deseq2 必填、组内恒定强制校验），`id_schema`（默认 `{sample}__{celltype}`，
informational）；`h5ad_export_matrix` 的 `layer`（默认 `X`）、`chunk`
（默认 2000 细胞/行组）。

## 布局

```text
pseudobulk/
├── manifest.toml
├── scripts/pseudobulk_counts.py
├── scripts/h5ad_export_matrix.py
├── Dockerfile
├── README.md
└── tests/            # pytest 套件 + 基准脚本（宿主跑，不进镜像）
```

镜像：`ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5`。
实际版本以运行态为准；该摘要的已核环境为 Python 3.11、AnnData 0.12.19、
SciPy 1.17.1、NumPy 2.4.6、pandas 2.3.3，不是 manifest 历史简写中的 AnnData 0.11。

## 整数与写出合同（2026-10-12）

`pseudobulk_counts` 实施 raw-count 求和，不实施均值、标准化、批次校正或
DE 推断。官方方法对照入口是 `scanpy.get.aggregate(..., func="sum")`；
本脚本不是 Scanpy 的全部聚合 API 实现。指定层、标签缺失剔除及 `min_cells`
是本插件的独立工程合同，不能以官方包默认行为掩盖差异。

输入整数的单值与每个供者×细胞类型×基因的总和必须在非负 int64 范围内。
风险路径以 Python 任意精度整数核查，包含重复稀疏坐标；不能靠单值阈值、
`float64` 总和或聚合后的正负号来排除溢出。允许的非整数分支始终不是
raw counts，聚合结果必须有限且非负。

基因名必须唯一、非空且无 TSV 控制字符。三输出路径须独立且不存在，
包括悬空链接；产物完成写入后以无覆盖链接发布。普通异常会按 inode
核对回滚本次发布，并清理临时文件；这不等于多文件 crash 原子性或持久恢复。

现有 `condition_column` 合同只检查供者×细胞类型组内恒定；它不自动证明
跨细胞类型的供者级设计合法。科学流程须独立审核供者身份、条件、库合并、
生物学重复及对比资格。也不能仅由矩阵数值判定 `.X` 一定是原始 counts：
正式研究须明确冻结 raw-count 层及输入来源。

隔离容器的小型验收入口（无缺依赖跳过）：

```bash
python3 tests/test_assurance.py /writable/evidence
```

该入口必须在 manifest 固定镜像中运行；完整作者对照、原失败复现与 native
DAG 证据另归档。已有宿主 pytest、合成小型对照均不构成真实规模验收或 G0。

## 口径（对齐 §15.3/§16，F07 收口后）

- **分组键是 `(sample, celltype)` 元组**，不做字符串拼接——拼接键会把
  `("donor__state","type")` 与 `("donor","state__type")` 合并成一组（审计
  F07 实锤，pytest 用例锁定）。输出 ID 仍是 `sample__celltype` 拼接串；
  不同元组拼出相同串时自动改百分号编码（`_`→`%5F`，故 `__` 只可能是连接符，
  ID 单射），log 记 `id_encoding=percent`。
- **校验覆盖稀疏矩阵全部存储条目**（旧实现只探前 10000 个）：非有限值
  （NaN/Inf）、负值 → 退出 2；非整数 → 默认退出 2，`allow_non_integer=true`
  才按原值求和并在 log 记 WARN（下游不得当原始计数建模）；基因名重复 →
  退出 2。
- **obs 标签缺失（NaN/空白串）显式剔除进 log**（`dropped_missing` 行），
  不静默并入任何组；一列全缺失才退出 2。这是二选一定死的口径：不报错、
  不合并，逐列计数可审计。
- `n_cells < min_cells` 的组剔除并逐组记 log（低细胞数组不进统计，
  防单细胞漂移伪装成生物学）。
- one-hot 稀疏矩阵乘聚合（`onehot @ matrix`），**导出按基因分块稠密化**
  （峰值 ≈ 块基因数 × 组数），不再一次性 `toarray()` 整个 groups×genes——
  旧实现该峰值随 基因数×伪样本数 无界增长，未实测（审计 F07-4）。
- deseq2 schema 下 `condition_column` 缺参/obs 缺列/聚合细胞内缺失值/
  组内不恒定 → 全部退出 2（设计变量必须干净）。

## 基准（2026-10-05，宿主 venv，python 3.14 / anndata 0.13 / pandas 3.0 / numpy 2.5）

`tests/bench_pseudobulk.py`：20 000 细胞 × 500 基因（nnz≈7.77M），
5 供者 × 4 细胞类型 = 20 组：

| 实现 | 墙钟 | 子进程峰值 RSS |
|---|---|---|
| main（旧，一次性 toarray） | 1.10 s | 433.8 MiB |
| 本分支（分块导出） | 1.59–2.35 s（3 次） | 433.7 MiB |

峰值 RSS 两版相同（由 h5ad 稀疏读取主导，≈ nnz×12B）；小规模下新实现
略慢（元组分组 + 分块写的固定开销）。渐近差异在组数×基因数大时拉开：
旧版一次性稠密化 groups×genes（如 5000 组 × 30k 基因 ≈ 1.2 GB float64），
新版块峰值 = `10^7 // 组数` 行 × 组数（同例 ≈ 80 MB）。

## 测试

```bash
python3 -m venv ~/.cache/fix-venvs/bulk
~/.cache/fix-venvs/bulk/bin/pip install anndata h5py numpy scipy pandas pytest
cd <本仓> && ~/.cache/fix-venvs/bulk/bin/pytest tests/ -v   # 14 passed (2026-10-05)
~/.cache/fix-venvs/bulk/bin/python tests/bench_pseudobulk.py
```

覆盖：元组键防碰撞（审计原始用例）、第 10000 条之后的非整数捕获（默认
错误 / allow 放行两路）、负值与 NaN/Inf、基因名重复、deseq2 表头与
condition 三种失败、legacy 兼容、min_cells 与缺失标签剔除、稀疏/稠密一致
+ 独立 groupby 金标准对拍、layer 选择。
fixture 注意：anndata 0.13 + pandas 3 写 object/categorical obs 列会丢
codes（codes 全 -1），fixture 一律用 pandas 默认 StringDtype 纯串列；
引擎 Rust 写的 h5ad obs 是纯字符串 dataset，回读不受影响。

## 冒烟记录

- `pseudobulk_counts`：6 供者 Poisson 梯度合成数据 D1≈214 → D6≈456
  单调恢复；稀疏/稠密矩阵路径一致（pytest 套件覆盖，见上）。
- `h5ad_export_matrix`（2026-10-04，biotools-py 容器内实跑）：
  引擎自产 lzf-CSR h5ad（sham_reannot，10794×21355）→ 24,376,851
  非零元、cell_id/基因符号正确；宿主 anndata 0.13 写的 h5ad（10×5）
  → 50 条全量导出。双向可读（lzf filter 32000 = h5py 官方插件 ID）。
