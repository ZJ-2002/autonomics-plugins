# B：pseudobulk 与 Scanpy 评分发布保全

状态：**SCOPED_DIRECT_AND_MICRO_DAG_PROVEN_DEPLOYED_SOURCE_VERIFIED_NOT_RESIDENT_EXECUTION**。
日期：2026-10-15。机器记录：`evidence/b-publication-ownership-20261015.json`。

本批修复两个原有 kind 的文件发布，不增加统计方法、研究分支或原 120 个候选
分母。直接容器、普通 I/O 控制及精确修复源码的四个隔离微型 DAG 已执行；
后续当前 `.3` 服务的装载源码身份已独立核实，但未从驻留服务实际执行方法验收。
这些不是完整单细胞研究链或全规模资源验收。
既有其他 A/B 插件的上线不能替代本批两个脚本的部署证明。

## 精确身份与不变的方法

基线是公开提交 `d91be9dad535e79c97fb3566b07fe1f68d0954ba` 中的原脚本。

| 原 kind / 文件 | 基线 SHA256 | 修复 SHA256 |
| --- | --- | --- |
| `pseudobulk_counts` / `plugins/pseudobulk/scripts/pseudobulk_counts.py` | `77884036871586b1be564a8c25f9ab72b2939a987db112aecd328cc86e44c83d` | `d1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109`（21,097 字节） |
| `gene_set_score` / `plugins/single-cell/scripts/score_genes.py` | `9cad19728810b8e9c9933fed33f556870419a985a12f1485ce61d4f4da8c58e8` | `dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774`（12,674 字节） |

两个原 manifest 均未修改：pseudobulk 为
`2c1a5d0105617aabed47b3950dfa751a94e3b47dfa7d98a805f9c5d1a66033c8`，
single-cell 为
`5288e9c7ac552f318b93c67f107fd45dcddf12d9396c38e00e6950e3bede9c42`。
端口、参数、默认 seed、raw 自动选择及声明的原资源预算不变。

pseudobulk 保留供者/样本×细胞类型的求和、整数边界、缺失标签及小组处理、
条件检查和 quoted TSV 身份。发布之前的原语句 AST 精确不变，摘要
`48d8d82f140b5bd67f17bc05fac521a36b7c56432cad78d3849bf07e95f8ceac`。
生产计算仍使用 SciPy 稀疏聚合；本轮不声称它改为调用 Scanpy 聚合，也不把
既往官方 `scanpy.get.aggregate(sum)` 对照冒称本次重新执行或全环境重装。

评分保留官方 Scanpy 1.11.3 `tl.score_genes` 原调用、控制池、
`ctrl_as_ref=true`、`n_bins=25`、`layer=None`、原随机种子和完整报告生成。
科学核心 AST（四个原 helper 与版本/参数/计算/报告语句）摘要为
`7f110c2c4b4ed5e5241ec4b29aaf9351549d926ae68312cadc42109e1de9f652`；
仅将读取输入文件的地址规范为占位符比较，因为修复后读的是已核验的解析目标。
这不是 UCell、singscore、供者差异检验或签名有效性认证。

## 已复现的破坏行为与修复

### pseudobulk：18 个实际 AST/I/O 观测，不是 18 次方法计算

档案 `90cd8c2be137412595dd47ebec644dae`，seal
`c054a3f2975e894ed61e0cd23b74286d7911bf5e4053164d669e05f376b4eddc`，
`CLEANED`、worker/launcher 0；9 个文件、93,731 字节已逐成员核对。
原/新源码各执行同样 9 个普通自清控制：正常发布、同 inode 改写后返回、
同 inode 改写后第二次链接失败、链接后暂存替换、链接后目标替换、
链接前暂存替换，以及 counts/metadata/log 三个写入前的暂存替换。

原脚本的 8 个故障控制中，7 个错误地正常返回，另一个虽抛异常却未保全改写内容；
不是“基线全部通过”。新脚本正常控制成功，其余 8 项拒绝且所有注入的外来
内容保留。总共是 18 个发布代码观测，不导入 AnnData、不聚合计数、不运行容器，
不以外层退出 0 给旧缺陷颁发资格。

修复在写入与发布前固定目录/文件/自有描述符身份和内容；文本只通过已核验的
自有描述符写入，避免检查后按名字重新打开并先截断外来替换。
链接后逐端口、最终完整集合及回滚检查原身份/大小/SHA；仅删除确认属于本次
发布且内容未变的文件，不按旧路径盲删，不重新认领被改写的 inode。

### gene_set_score：真实输入丢失、覆盖与半成品

旧脚本直接写 H5AD 后写报告。真实固定镜像中的三个基线控制确认：
报告路径等于输入时，方法退出 0 却把原 H5AD 替换成 JSON；两个已有输出
被覆盖且退出 0；报告父目录不存在时退出 2，却留下可读正常 H5AD 半成品。
修复后三项均明确退出 2，原始输入/已有哨兵不变，没有新正常输出。
不是以仅观察到非零退出代替特定诊断、字节保全和无产物检查。

修复预检输入/输出别名、已存文件及父目录；实际读取已核的解析输入，
在计算/发布前后复核绑定与内容。暂存文件独占创建并保留自有描述符。
AnnData 写入地址为 `/proc/self/fd/<owned descriptor>`，文本经自有 fd 写入；
命名暂存入口被替换也不会使 writer 先截断另一个 inode。
写前后、链接后和最终检查均验证身份/内容；失败只回滚确认的自有产物。
暂存清理不递归删除未知目录，保留外来替换、未知成员和同 inode 内容变化。

这些都是观察检查点，不是永久防篡改、对所有敌对并发竞态的保证、跨文件
crash-atomic 事务、断电恢复、持久缓存或自动撤证证书。

## 最终固定镜像直接运行

最终档案：`3916f488e09e4ded99b39890cfc4cf68`；seal
`001806a1bd052088aefe6e663624c6b859d6252b8b839779e45569f332f568ef`。
状态 `CLEANED`，worker 与 launcher 均为整数 0。
473 个普通文件、2,761,767 字节的完整成员、大小与 SHA 已独立核对。
证据和合成产物保留于私有档案，本文不发布 launcher 日志、研究数据或凭据。

使用两个**顺序**容器，共 102 次方法子进程；不是 102 个容器、DAG 或节点。
实际默认受管 backend 的两个唯一 ownership intent 均已 reconcile，剩余容器为 0。
每容器 1 CPU、1 GiB、禁网、只读根文件系统，禁拉取；无新构建、安装或依赖环境副本。
外层服务实际 `memory.max=2,147,483,648` 字节，kernel peak 1,168,334,848 字节，
max/OOM/kill 事件均为 0。此为本批小型运行，不认证原 manifest 的 8 GiB/多 CPU
声明、全主机预算或真实规模性能。

### pseudobulk：原/新各 41 个案例

固定镜像为
`ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5`，
实际 AnnData 0.12.19、NumPy 2.4.6、SciPy 1.17.1、pandas 2.3.3。
两版分别执行原 20 个正例和 21 个指定拒绝控制，合计 82 个方法子进程。
21 个拒绝中 20 个退出 2；注入的普通第二次发布失败退出 1。
不能把它们写成“全部退出 2”或要求生产方法在故障注入后正常返回。

20 组完整 counts 与 quoted sample metadata 在新旧间逐字节相同，并通过原合成
算术/身份参考检查。覆盖 dense/CSR/CSC、类型及整数边界、命名层、最小细胞数、
legacy、缺失标签、冲突 ID，以及引号、逗号、字面 NA、前导零和 Unicode。
完整日志只规范掉已知的原输入路径差异，其他内容均保留比较。
这是原数值与序列化行为回归，不是新供者设计、DESeq2 推断或独立再安装的作者环境。

### Scanpy：原/新各 7 个原案例，加 6 个真实路径控制

固定镜像为
`ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20`；
实际 Scanpy 1.11.3、AnnData 0.11.4、NumPy 2.1.3、SciPy 1.14.1、
pandas 2.2.3、h5py 3.16.0。两镜像均核实际 manifest/configuration/有序 layer 身份；
本轮复用已有作者包，不冒称重新下载或逐文件重新鉴定整个安装。

原科学套件源码不变，SHA
`36fd415ea047213c022c0c4fe781e7b70295255277162afda903debbe6ccb78c`。
新旧各执行全部 7 个测试，无跳过/失败/错误：未截断的 ctrl_size、稀疏、raw 轴、
缺失/重复成员、非有限评分摘要、无控制基因、obs 名称冲突。
其中各含 5 个数值正例和 2 个预定拒绝；14 个测试通过不等于 14 次方法成功。
比较仍直接调用官方 Scanpy 参考，评分容差保留 `atol=1e-12, rtol=0`。
加上上述原/新各 3 个真实 H5AD 路径案例，共 20 个评分方法子进程。

另在同一固定环境中实际调用 AnnData `write_h5ad` 写自有 `/proc/self/fd`，
再读取完整 12×100 X 与 obs/var，保持原 inode。该兼容性已实测，
不再只依赖普通 byte-writer toy；它不等于所有 AnnData 编码或全 HDF5 层级认证。

## 修复源码的四个隔离微型 DAG

档案 `4c608817b50f4720a52d4b470354f8d9`，seal
`43439641bed58551608889244e60f6f67fdd024116de1b82e72a5bc30cf8a4bb`，
`CLEANED`、worker/launcher 整数 0；146 个普通文件、635,959 字节已独立逐成员
重算 SHA。两种原 kind 各有一个正例和一个特定方法拒绝：每图 2 节点、1 条边，
共 8 份自有任务回执、4 条实际绑定、5 个正例输出端口。
两个正例方法实际退出 0；pseudobulk 的缺失 condition 列和评分的无可用控制
基因各实际退出 2，保留特定诊断且未发布正常输出，不是用任意容器失败代替方法拒绝。

复用已封存 23-guard runner，SHA
`636d3eb57391f0ed60d8da976b06a2d63a699bed40dd96b30ce67333d50aa22b`；
实际 SDK 候选 `4256643c55ae6fb50e8c867069330ed6ac2b4bc0` 的父提交为
`11f061589473cb8e4fa57d364ad7107108245de1`。未启动新的构建，未借用旧 SDK
回退。原 manifest 与修复脚本身份均保持上述固定值，File 输入经过精确自有
symlink staging 核验，而非拒绝所有合法暂存链接或接纳任意目标。

pseudobulk 正例的全部计数与供者 metadata TSV 与此前封存的 direct 正例逐字节
相同。评分正例的完整报告逐字节相同，另一个实际固定镜像比较容器回读完整
AnnData/HDF5，检查 1,212 个有限数值及完整结构、轴、属性和数据。
此比较的参考文件虽然命名为 `fresh-author.h5ad`，实际来源是上述 direct 档案
`score/original-existing-output/output.h5ad`，即已封存旧节点产物；不是本轮新调用
官方 `score_genes` 得到的独立参考。独立官方评分数值证据来自前节原/新各 7 项
套件，两种证据不能混称。

评分原家族声明的 CellTypist panel 在本方法中不被读取。本轮显式挂载只读的
`autonomics-technical/unused-celltypist-nonmodel-marker`，内容是 `NOT_A_MODEL.txt`；
它既不是模型，也不授予 CellTypist、真实 panel 或注释资格。4 个方法容器和
1 个完整对象比较容器均通过默认受管 backend 的各自 intent 核实停止，剩余为 0；
worker 内临时 launcher 只转发原受管 shim 和该 backend，不切换生产配置或私有 A/B store。

四图原生内存监控实际采样分别为 13/9/37/29 次，来源 `cgroup_v2`，无监控错误或
阈值触发；服务父限制为 2 GiB，kernel peak 为 1,206,243,328 字节，max/OOM/kill
事件均为 0。原 OCI 声明仍分别为 pseudobulk 4 CPU/8,000,000,000 字节和评分
2 CPU/8 GiB；这不认证该全规模资源。8 份实际 `task.json` 的原生任务请求均是
`resources: {}`，不能宣称 manifest 资源已映射为原生调度准入或得到同等预算批准。

## 后续当前服务源码装载观察

前述 direct 与微型 DAG 档案均是在本批源码尚未部署时封存；不能改写其历史范围。
随后于 `2026-10-15T09:51:09.690726+00:00` 完成两次连续只读健康观察：
`/api/v1/gateway/status`、`/api/v1/agents`、`/api/v1/plugins` 均返回 HTTP 200，
当前为 `v0.1.0-research-preview.20261015.3`、PID 992480，8 个 agent 全部 idle，
登记 35 个家族。当前二进制 SHA 为
`ced5e4d1bc333c8de136d7fbc16107f4e88d29b0d30990d29486d5579ed1d7f2`。

两个本批家族现在均使用 Git+完整 rev+subdir：
`d3065953a513f5b5f07e436b8ff2da62177341cd`；干净固定 checkout 中全部
82 个 tracked 文件已与精确 Git 对象逐字节复核，包括上述修复脚本。
其余 33 个配置条目未改；先前 A/B 三核心家族的 25 个文件仍固定于 `cb594425...`。
这是当前实际服务暴露身份和装载源的证据，不是 `resident method execution`、
新二进制全域验收或新科学结果。

独立私有记录为 `INDEPENDENT_CURRENT_RELEASE_OBSERVATION.json`，摘要
`802829f2452f04db8430af27fd1452b82d42777fe2f8e560197a99787dac27ac`。
用户已确认保留当前 `.3`。它是另一条后续切换链，不能归因于此前启动 `.1` 的
launcher：该启动等待进程曾由操作者代理主动终止、实际退出 143，不能填写
“启动命令成功退出 0”；当时 daemon 与当前 `.3` 的切换原因未独立推断。
本次独立观察没有重启、修改配置或凭据，也没有运行研究或公开密钥/原始代理响应。

## 未结与研究边界

- 本批精确新源码已完成上述固定 SDK 微型 DAG；完整研究链、全部参数/数据域及真实规模仍未认证。
- 本批新 wrapper 当前装载源已核实；实际驻留方法计算、缓存及恢复仍未获证。
- 不改原 120 个候选、冻结签名、276/288/696 名单、查看史、分组或统计设计。
- pseudobulk 仍须另核 raw-count 层、供者/动物身份、技术库合并、低细胞组、
  跨细胞类型条件、完整检验家族及对比资格；允许非整数分支不是原始 counts。
- 细胞层描述性 Scanpy 评分不是 UCell、B-SPEC singscore、供者级疾病推断或签名特异性。
- B-S 保持 `CONDITIONAL_NOT_READY`、GS01 保持 `OPEN`；不执行正式空间假设检验。
- 无真实科研拟合、科学授权或 G0 放行；技术证据不能填补未决的科学合同。

