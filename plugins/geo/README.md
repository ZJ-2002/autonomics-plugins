# geo

GEO/SRA 公共数据下载源节点。补齐引擎缺口：原 registry 无任何 GEO/SRA
下载工厂，主计划的数据集获取（GSE 系列矩阵、SOFT 元数据、SRA run 表）
此前只能宿主机 curl。2026-10-04 增补 `geo_suppl`：系列 suppl/ 目录下
任意具名补充文件（LINCS/CMap 的 GCT/GCTx 矩阵由此进 DAG，方案 §18.2）。

## 节点（全部零输入、Egress、既有输出拒绝覆盖）

| kind | 输出 | 上游 |
|---|---|---|
| `geo_series_matrix` | `series_matrix.txt.gz` | `ftp.ncbi.nlm.nih.gov/geo/series/GSE130nnn/GSE130563/matrix/`（示例） |
| `geo_soft` | `family.soft.tgz` | 同上 `soft/` |
| `sra_runinfo` | `runinfo.tsv` | 官方 SRA backend `runinfo?acc=` CSV，逐字段转换为 TSV |
| `geo_suppl` | `suppl_file`（原名字节，不解压） | `…/GSE92nnn/GSE92742/suppl/{suppl_file}`（示例） |

参数：`accession`（string，必填；GEO 节点仅 GSE；RunInfo 接受 GSE/SRP/SRX/SRR，
不接受 PRJNA）；`geo_suppl` 另有 `suppl_file`
（suppl/ 下确切裸文件名，拒绝路径分隔符、控制字符及 `.`/`..` 整段；
合法 `a..b.txt` 不拒绝；`.gz` 后缀时校验完整 gzip CRC，HTML 响应拒绝）。
`geo_series_matrix.matrix_file` 可明确当前系列的平台文件名，默认 canonical 文件，
不自动择平台。`sra_runinfo.sra_accession` 仅可选择官方 GSE self-SOFT 关系集内
的 SRP；唯一关系可技术解析，无/多关系不猜，不授予科研资格。`geo_suppl` 超时 28800s（LINCS
Level5 全量 gctx.gz 为 GB 级）。

## 布局

```text
geo/
├── manifest.toml
├── scripts/geo_fetch.py   # 单文件自足：下载与清单节点经 GEO_MODE 复用
├── Dockerfile
└── README.md
```

镜像以 manifest 的不可变 digest 为准：`ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5`。

## 实现说明（引擎契约踩坑）

- `script_file` 被内联成容器内单一脚本，`scripts/` 目录**不挂载**——
  共享模块 import 不可行，故本家族共用一份自足脚本、以 `GEO_MODE`
  环境变量分派。
- 暂时网络错误至多 3 次重试；永久 HTTP 错误不猜资源；边下边算 sha256，
  完整 gzip CRC、系列身份和格式结构校验后以 hard link 无覆盖发布单个文件；
  每个 matrix 表必须含完整样本 header，失败仅清除匹配本次 fd/inode 的 partial。
  外来 regular/symlink 替换被拒绝且保留，不截断外来日志；不是输出对的事务提交。
- `family.soft.tgz` 是兼容原端口的 basename，真实内容为官方 `.soft.gz`
  的 gzip SOFT 文本，**不是 tar**。`suppl_file` 是原固定输出 basename，
  上游文件名保存在日志，不改端口为参数值。
- RunInfo CSV→TSV 保留每个字段的原始字符串（含前导零、NA 字面值及引用字段），
  日志分列记录原始 CSV 与转换 TSV 的字节数/sha256；GEO 输出保持原字节不转码。
- 格式和下载通过不证明队列、供者、生物学重复或研究方案资格。详细范围与未结项见
  `RESOURCE_CONTRACT.md`。`python3 -S scripts/test_geo_fetch_contract.py` 为轻量离线合同测试。

最新修复的宿主 stdlib 回归不能继承旧脚本的固定镜像/native DAG 通过状态。
完整新源码执行、实际服务部署及研究放行必须分别验收；inode check/unlink
间隙仍非敌对 TOCTOU 保证，同路径并发、崩溃恢复、永久缓存复用均不由此认证。

## 冒烟记录

- 实网下载 GSE18832：HTTP 200、863080 字节、gzip 合法、sha256
  `0e9995eb…` 自锚入 log。
- `geo_suppl`（2026-10-04）：GSE92742_Broad_LINCS_gene_info.txt.gz →
  200 / 216692 B / sha256 `741216cc…`，gzip 解压后即 LINCS Entrez↔符号
  映射表（cmap_connectivity 的行标识符映射上游）。
