# Frozen A：完整家族三阶段直接运行证据（草稿）

状态：**DRAFT_DIRECT_RUNTIME_PROVEN_ISOLATED_DAG_PENDING_NOT_DEPLOYED**。
日期：2026-10-15。配套机器记录：
`evidence/frozen-a-complete-family-20261015.json`。

本记录只证明下列精确源码、冻结输入身份与技术场景的三阶段直接容器运行；
真实隔离 DAG 的端口连线、失败传播与当前 daemon 装载仍待验收。
文件名中的 complete 指每个家族的完整成员与分母，不代表整个 A 研究完成。
本文是待补 DAG 证据的草稿，不是正式科研准入证书。

## 方法与三个执行 kind

| 阶段 | kind / 源码 | 功能与边界 |
| --- | --- | --- |
| 组装 | `frozen_a_family_assemble` / `research-adapters/frozen-a-family-assembly` | 核九份冻结来源，调用原 `execution_utils.py` 的 `primary_p`、`strict_conjunction`、`assert_locked_ids`，按冻结登记顺序组装 564 行与六个完整校正向量；不拟合 MR，不填补 O 类资格 |
| 官方校正 | `frozen_a_family_adjust` / `research-adapters/frozen-a-family-adjustment` | 只提取原 `g0_v432_methods.R` 唯一 `adjust_full` 定义，调用实际 R/stats 4.6.1 `stats::p.adjust`；不 source 整份科学程序，不用 Rust/Python 重写 BH/BY |
| 发布 | `frozen_a_family_publish` / `research-adapters/frozen-a-family-assembly` | 重新核原登记表、全部 ID、原始缺失、完整分母、校正行与官方回执，输出全家族表和完整校正向量；不在 Python 再算 q，不把传输成功变成科学资格 |

上述三个工程执行 kind 服务于原固定候选行 17/18 的完整多重校正与严格路径
合取合同，不是新增三个被认证的统计方法，也不把原 120 个候选分母改成 123。
特别是本次有限冻结适配器，不构成同名通用 `hypothesize.*` 节点全参数域认证。

四家族大小依次为 88、188、36、252；两类边分别执行 BH 和 BY，两类路径
只执行 BY，合计六向量、每场景 840 行。组装表保留全部 276 边与 288 路径。
严格 IUT 为 `max(p_XM, p_MY)`；任一成分缺失则原始路径 P 保持缺失，
不以另一条边、`p_XY`、乘积或显著性筛选代替。原始 NA 在 TSV/RDS 中保留；
仅冻结 `adjust_full` 的校正输入将不可估计值以 1 占分母。
这不是宣称 `p.adjust` 本身自动采用 NA→1 规则。

## 精确受测源码与运行环境

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| `research-adapters/frozen-a-family-assembly/manifest.toml` | 2770 | `a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf` |
| `research-adapters/frozen-a-family-assembly/scripts/family.py` | 26707 | `3370bf9a604de0c3e6acab9e1e7617f7caba579c6630e96f17e0d2f4c002d1ba` |
| `research-adapters/frozen-a-family-adjustment/manifest.toml` | 1636 | `55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da` |
| `research-adapters/frozen-a-family-adjustment/scripts/adjust.R` | 21205 | `debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412` |

原始 R 文件 SHA256 为
`f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd`；
提取定义（含末尾换行）SHA256 为
`2d110232f5f1c3097d763686df1ecec5212e3ca18b4b226ac8f5562c388813fd`。
R 实际校正环境是已有固定镜像
`ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d`；
镜像名称不表示本阶段调用 MRlap。Python 两阶段使用已有固定官方 CPython 镜像。
各方法容器单 CPU、1 GiB、禁网、只读根文件系统、禁止拉取镜像。
这些是直接方法容器的运行限制，不是整个主机、daemon 或未来 DAG 的资源证明。

R 节点只接收四个输入；它可核上游九源的声明及四个实收文件身份，不能独立重读
另外八份原源文件。九源内容身份及真实登记顺序由实际组装/发布阶段分别核对。
不能将只检查上游 JSON 声明称为独立的全源复核。

## 已完成：三场景直接方法运行

唯一最终直接运行档案：`1dd93528d56d4cbe8a18e63247b0c2ee`，
seal（`artifacts/MANIFEST.json` SHA256）：
`93fdedb6434a3ab570cec95e400909ef8b12408819be1acc33732b01dfbf0ccb`。
状态 `CLEANED`，worker 与 launcher 均为整数 0。
独立审核已逐项核完 183 个普通文件、2,582,799 字节，确认无漏项、额外文件或哈希差异。
档案私有；本文不发布研究源文件、容器启动日志或当地路径。

| 场景 | 实际 scope | 三阶段结果 |
| --- | --- | --- |
| `BOUNDARY` | `SYNTHETIC_NOT_RESEARCH` | 三方法均成功；564 家族行、840 校正行 |
| `INTERIOR` | `SYNTHETIC_NOT_RESEARCH` | 三方法均成功；564 家族行、840 校正行 |
| `REAL_FROZEN_NA_LEDGER` | `FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH` | 只机械传输真实已见冻结账本；全部原始 P 仍缺失，校正占位为 1；不产生估计资格 |

这是三个场景、两个允许的技术 scope，不是三项研究授权。真实账本不能借技术
运行将 275 个待定重叠类别改成可估计，也不能因 O1/MRlap 不可用改用 IVW 主结果。
条件 MVP 分支、来源角色、查看史和已见历史性质不变。

九次正向方法执行全部退出 0。另有十六次真实方法拒绝，全部退出 2，
每次都核固定 kind/镜像、特定错误诊断、非空声明失败日志及无正常产物：
错误家族、外来 ID、布尔 P、越界 P、混合行 scope、混合行 scenario、
伪研究 scope、缺失 ID、重复 ID、非有限 P、改动冻结源、缩短向量、
路径误用校正方法、错误 R 版本回执、非有限 q、预存外来输出。
最后一项的 27 字节外来文件保持原内容摘要。
OOM、权限或容器启动错误不计作这些方法合同拒绝。

共 25 个方法容器实际退出；组装 14 次、R 校正 5 次、发布 6 次。
25 个唯一 ownership intent 与停止记录一一对应，最终均零剩余容器。
三阶段是顺序直接调用，不能把 25 个方法案例称为 25 张 DAG 或 25 个认证节点。

## 独立官方数值与完整 RDS 回读

固定官方参照来自已封存的 `ab47448d3e7b49bc96610c3529d94257`，seal
`22387c3e20caecb8eaee9e671fa4a78a3e28c7d690f66bd300e5c7726095a048`；
其全部 21 文件、896,556 字节重新核对，不重生或修改 golden。
各场景全部 840 行的原始 P、ID、方法、顺序逐项一致，合计 2520 个 q 值
与旧官方参照数值完全相同；发布的完整校正向量与 R 阶段输出字节相同。

另一个官方 R/stats 4.6.1 **宿主进程**回读三个完整 RDS；这不是额外三个容器。
检查全部 18 个向量、2520 个值，以及完整向量键、分析 ID、原始 NA mask、
占位输入、方法、分母、四输入 SHA、原调整定义字节和版本。
q 同时与旧官方参照及独立实际 `stats::p.adjust` 调用精确相等。
将 INTERIOR 错指 BOUNDARY RDS、或篡改期望输入 SHA 的两个读回反例均实际退出 1，
分别触发向量键与输入身份的指定断言；不是把任意读回失败当作反例通过。
这证明调用与结果传输一致，不是重新验证 BH/BY 的所有统计理论或未知输入域。

九份冻结来源运行前后完整身份/摘要不变，独立复核时仍相同。原只读全项目
验证器实际再次退出 0：46,786 次检查、23,669 个唯一文件；其输出仍明确
`all_project_scientific_gates_passed=false`、`scientific_truth_certified=false`。
本次不读取原始 GWAS、不拟合 MR、不赋新重叠资格、不改冻结分母或科学签署。

## 待补与部署隔离

- **隔离 DAG：PENDING。** 尚未以本批精确源码完成实际三 kind 的 DAG
  全端口、内容身份与失败传播证明；本草稿待根代理实际完成后补证。
- **这三种新 family kind：未部署。** 不能用直接容器成功代替 resident daemon
  注册/装载身份、生产运行或科学放行。
- **原有三套核心 A/B 插件：另项管理。** 操作者之后允许生产重启，原有
  `twosamplemr-v432-a`、`bulk-limma-normalized`、`frozen-b-project` 的精确来源
  切换及装载验收属于独立工单；其重启成功不自动部署或认证本批新 family。
- **空间模块：不变。** B-S 继续 `CONDITIONAL_NOT_READY`，GS01 继续 `OPEN`；
  不执行正式空间检验、不替方案锁定零模型。
- 技术通过不是 G0 PASS，不改变 276/288/696 名单、查看史或未决科学条件。

