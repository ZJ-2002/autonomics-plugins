# 固定官方区域分析适配节点

这是 staged 技术实现，未安装至生产 daemon。使用已有缓存镜像中的
**susieR 0.14.2 / coloc 5.2.3**，不声称与另一个 susieR 0.16.6 部署或当前
最新版本所有方法等价。官方源码的固定提交及安装函数体/参数比较随证据包封存。

两个节点均有三文件输入和五个声明输出。第三输入必须是严格的 TSV：
`key\tvalue`，每个 key 一行、唯一且非空；不存在默认样本量、LD、尺度或
对齐推断。不支持的参数、畸形 TSV、重复/空变异 ID 和未验证的文件哈希均阻断。
变异 ID 使用 ASCII 字母、数字、`_.:+-`，保留 `0001`、`1e03`、`NA` 原始身份。
每区 2–2000 个变异是本适配器的工程范围，不是官方包的全部输入域。

## 通用合同

- `operation`：`susie` 或 `abf`，须与节点一致。
- `scope`：`TECHNICAL_ONLY_NOT_G0`。
- `input0_sha256`、`input1_sha256`：实际两个输入文件内容 SHA256。
- `alignment_evidence`：冻结的效应等位基因、build、祖源和尺度证据身份。
  非空字符串不是这些科学资格已经核验的证明。

## `cachexia_susie_rss`

输入 0：`snp,z`（Wald z）或 `snp,beta,se`（定量性状效应）。
输入 1：有符号相关矩阵 TSV，首列 `snp`，其余列名与行 SNP 必须严格等于
输入 0 顺序。矩阵必须有限、对称、PSD、单位对角；不下载 LD 或回退单位阵。

必填合同：`mode=z|beta_se`、`effect_scale=STANDARDIZED_Z_WALD|QUANTITATIVE_BETA_SE`、
整数 `n>=3`、`L=10|20`、`coverage=.95`、`ld_source=reference|in_sample`、
`estimate_residual_variance=true|false`、`scaled_prior_variance`、
`estimate_prior_variance=true|false`、`min_abs_corr`、`max_iter`、`tol`、
`n_purity`、`seed`。`beta_se` 另需正的 `var_y`，`z` 不接受未使用的 `var_y`。
reference LD 不能在本路线估计残差方差。prior method 固定为 optim、refine FALSE；
不能在合同里写 EM 后静默执行 optim。

输出：逐变异 PIP/全部可信集归属、固定列结构的 CS 成员/覆盖率/纯度 TSV、
完整 fit/arguments/contract RDS、日志、审计 TSV。没有可信集明确记录，
不是非收敛；同一变异可属于多个集合，不以单整数覆盖前一个归属。
非收敛将 fit 留为 `.diagnostic`，日志和 BLOCKED audit 保留，但不发布成功分析端口。
RDS 中保存 alpha、mu、ELBO 和官方 sets 等字段，输出不冒充效应的原始测量尺度。

## `cachexia_coloc_abf`

输入 0/1：`snp,beta,se`，两表必须是同一有序 SNP 集合。必填 `n1/n2`、
`type1/type2=quant|cc`、`p1=p2=1e-4`、`p12=1e-6|1e-5|1e-4`。
quant 需已知正的 `sd_y1/sd_y2`，cc 需 `(0,1)` 的 `case_fraction1/case_fraction2`；
相互冲突或未使用的尺度键拒绝，不用 MAF 自动估计 SD。

输出：完整 H0–H4/变异数 summary、官方逐变异结果、完整 RDS、日志和审计。
官方结果可能按 SNP 排序；按 lexical 集合及官方参考核验，不假称维持原行序。
这是每性状单因果变异假设下的方法，**不替代 coloc.susie**、三性状同信号桥接，
不把 PP.H4 阈值当 FDR 或因果结论。

所有失败清除成功分析输出，仅保留诊断；审计将 G0 明确置 false。
技术测试不决定正式研究区域、祖源/等位基因/尺度资格、版本冻结、家族分母或启用条件。
