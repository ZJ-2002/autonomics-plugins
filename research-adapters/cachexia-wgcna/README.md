# WGCNA 官方路线与验收边界

本目录未注册正式部署，未写入 `~/.autonomics/plugins.toml`。manifest 采用真正
构建完成的 `localhost/cachexia-wgcna@sha256:017ccc15a033fd98f84b738c4a94c45607d358060eb5ee5bb091d3a0f8828ec9`，
没有可变标签或占位镜像替代。节点认证以独立最终封存证据为准，不以本目录存在为准。

## 方法及输入

- 原版 CRAN WGCNA 1.74，完整 source SHA256
  `4f61e117b82287f01b61bf936d5c5ea3814c9c4b0d0b90d5016dda77f1f955d6`。
- 三个 File：`gene_id` 开头的 gene×donor 表达 TSV；按表达列序排列的
  `sample_id/donor_id/tissue/group` 元数据 TSV；35 键冻结 JSON。
- 独立供者表达尺度必须显式声明。只接受技术合成或已见历史数据，不推断新研究
  资格、疾病模型、供者独立性或协变量调整。单组织、20–128 供者、10–1500 基因
  是本轮技术证明预算，不是全研究资源能力认证。
- 官方 goodSamplesGenes 先核验；允许剔除时，仍保留原始全部供者与基因身份及
  mask，不能把剔除后的行数冒充原始家族分母。`NA` 表达缺失不等于文字 `NA`
  基因 ID；不做零填补、名字合并或隐式标准化。
- 固定 power 与官方 pickSoftThreshold powerEstimate 两条合同分开。后者返回
  NA 时阻断，不降 R²、不换最小 power；诊断保存实际扫描对象与 RNG。
- blockwiseModules 的参数显式冻结；原版算法及内部 warning 行为不改写。
  全部 grey/未分配模块、实际 blockGenes、完整 MEs、signedKME 保留。
  不是所有 WGCNA API/default 参数、权重、consensus、保存 TOM 复用或临床模型认证。

## 八个输出

| 端口 | 含义 |
|---|---|
| 0 | 官方扫描/ME/kME 投影与真实模块/邻接/TOM 文件统计，逐字段类型、坐标及缺失子型 TSV |
| 1 | 完整原始输入、全部返回模块对象/树/邻接矩阵/TOM、RNG、warning、合同 RDS |
| 2 | 内容身份、技术状态、错误和不授予 G0/科学放行的 audit JSON |
| 3 | 非空方法/阻断日志 |
| 4 | 完整原始基因顺序、QC、实际 block、模块、grey/未分配状态 TSV |
| 5 | 完整原始样本/供者/组织/组顺序、QC 状态 TSV |
| 6 | 真正由官方 saveTOMs=TRUE 写出的每个 block TOM 原文件 tar.gz，不是 net 对象大小 |
| 7 | 单项技术 family/test ID 及状态 TSV；不是研究 276/288 家族重定义 |

有效 ID 的失败保存在 workspace 的 `blocked-family.tsv` 及 audit/log；扫描未可估计
另保存 `nonestimable-power-scan.rds`。失败删除正常估计端口，不发布正常 P 或伪成功。

## 当前证据边界

已建立原版 source closure、固定镜像、输入/类型合同回归和独立 fresh 包完整
重算脚本。方法通过仍须真实七节点 DAG、完整数值/实际产物重算、旧包装器
根因反例、独立最终审查及封存；这些状态应查阅对应 `results/cachexia-v4.1`
最终封存记录，而不是根据脚本或镜像数量推断。未封存不得计入已证明数量。

历史不可获取的旧 digest 不能被本目录环境冒充：对旧脚本的任何新环境反例必须
标明 counterfactual，不能称为原旧镜像或 resident daemon 实验。
