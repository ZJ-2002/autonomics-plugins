# sensitivity / permutation 固定 digest 迁移候选

此目录仅供主会话审阅和统一集成。两份 patch 各仅改对应旧 manifest 的一行 `image.reference`；旧 manifest、脚本、生产插件 pin、qualified profile 均未修改。`migration-plan.json` 记录实际源文件 SHA 和应用补丁后的预期 SHA。目录本身不是可加载插件。

| 源 manifest | 补丁 | 目标固定远端身份 |
|---|---|---|
| `research-adapters/cachexia-sensitivity/manifest.toml` | `cachexia-sensitivity.patch` | `ghcr.io/zj-2002/sensitivity-official@sha256:09ff878b31f5709e60a287958e666025c0daa0ba31124d707dbff38e11dc2cbd` |
| `research-adapters/cachexia-permutation/manifest.toml` | `cachexia-permutation.patch` | `ghcr.io/zj-2002/permutation-official@sha256:58d2e4d969549713bf8c85c22f3d672305fac39e6ded19fe9f9cbe92f713b7a7` |

当前全部 `research-adapters/*/manifest.toml` 中，仅上表两处引用对应旧本地镜像。前者提供 `cachexia_evalue_official`、`cachexia_combine_pvalues_official`；后者提供 `cachexia_permutation_official`。typed 伴随节点 `cachexia-sensitivity-typed-values/cachexia_sensitivity_values_to_parquet` 独立使用 `localhost/autonomics/single-cell-preprocessor@sha256:5069c3ffaac0b11dfe950c1cd026f4195317be47b529b730572d9e670ad0f59b`，保留原样。permutation 已直接输出 Parquet，无需假设另有同镜像 typed 伴随节点。

封存发布证据分别来自 session `12640e645fb140ec99f3104213213b3b` 和 `61ab89f3ba47406cb6dc6b4ba3be7d8f`。seal、verification SHA、config SHA、顺序 RootFS 摘要及映射在计划内。验证器只读回核这些小型档案全部文件、退出码和映射；不会复核全量 OS 文件或重复方法验证。两份既有 verification 均记录同内容远端身份已核对、匿名 manifest 读取失败。本候选不重新请求 registry；公开访问保持 **PENDING**，不能称为 public。

## 增量验证

从主仓执行：

```sh
python3 -B scripts/research_validation_session.py run -- python3 -B /home/zj-normal/Work/autonomics-plugins/research-adapters/image-portability-deployment-v1/validate_candidate.py
```

共新增 10 个 unittest：两份档案回读；实际源文件身份；两份补丁的真实 `git apply --check`、应用、结构比较和反向恢复；全目录旧镜像消费者扫描；typed 伴随节点不变；非镜像字段变更拒绝；过期源 SHA 拒绝；错误目标 digest 拒绝。非镜像变更负例覆盖资源、超时、输入端口、命令/参数。结构比较删除且仅删除 `image.reference` 后要求完整 TOML 对象相等，字节补丁也必须严格等于单行替换生成的 diff。仅在会话 `TMPDIR` 建立两个小型 manifest 副本，无容器、镜像、统计或服务调用。

永久技术证据写入 `AUTONOMICS_VALIDATION_PERMANENT/image-portability-deployment-v1/verification.json`，包括受测候选副本及 SHA。最终封存定位另见测试后补写的 `EVIDENCE.md`；该文件属于文档增量，不是测试时源码。测试失败档案同样保留。

## 由主会话执行的最小部署与回退

1. 先复核计划内 source manifest 和 script SHA，再在主会话集成工作区逐份 `git apply --check`。只在与这些 SHA 一致的源文件上应用补丁，核对 candidate manifest SHA。源文件漂移时停止集成并审阅差异，不能用模糊替换跳过身份检查。
2. 用户统一发布后记录**实际包含两处新 digest 的插件仓完整提交 SHA**，再以该固定 rev 安装。计划所列插件基线 HEAD `d8c06ac1c45ec042a6413f1388c6d826b0dabd33` 仅作起始位置；当前候选未提交，该 HEAD 不代表已含补丁，不能当作部署 rev。主仓基线 HEAD 同理不能代替实际构建文件 SHA。发布固定 rev 及受影响 release-lock/catalog 更新均为 **PENDING**，本会话不编辑它们。
3. 主会话协调 GHCR 公开权限，或使用经批准的既有私密认证路径，按精确 digest 完成目标机器镜像准入。不得用 tag 漂移、改 digest 或放宽校验解决访问失败。本候选保持 `pull_policy = "never"`，所以远端 manifest 存在不代表目标宿主已缓存该精确引用；安装/导入及身份核对为 **PENDING**。本会话不拉取、不构建、不推送。
4. 按项目已有安装流程由用户统一处理插件 pin 和生产切换；保持方法、参数、ports、resources、scripts 不变。记录先前生产固定 rev 与实际加载身份，作为回退目标。用户需要变更 resident 时由其安排，本候选不执行服务控制。
5. 回退时主会话恢复先前固定插件 rev/安装状态，或在精确 candidate SHA 前提下反向应用两份补丁并恢复原固定 pin。旧本地镜像引用和所需本地缓存必须仍可用；本候选不删除镜像或既有缓存。恢复后执行同一只读装载身份核验，不运行统计。

## 一次只读 resident 装载核验设计（尚未执行）

核验必须针对实际生产 resident 的进程内 registry，而非从磁盘另开一次 loader 冒充 resident。部署窗口由主会话收集：resident executable 路径/文件 SHA 与对应构建 rev、已安装插件固定 rev、受影响四个 `plugin/node` 完整地址（上述三个方法节点和保留的 typed 节点）、每个节点实际加载的 manifest SHA、script SHA、image.reference；对照计划中的 candidate SHA、新远端 digest 和 typed 原身份。核验不得提交 DAG、创建研究 task 或调用节点执行。

当前现成只读入口 `list_node_factories` 只返回地址/简述；`get_node_spec`、`get_node_ports`、`get_node_doc` 可核对接口，均不足以读取完整 loaded `PluginIdentity`。读取磁盘文件 SHA 也不能证明旧 resident 已加载新内容。因此地址/端口核对仅为接口观察，完整 resident 身份核验为 **PENDING**。若现有受保护诊断入口仍无法提供这些字段，需由主会话另行安排同一 resident 内的只读身份观察；不可声称已经通过。

现有 `crates/container-plugin/examples/research_manifest_registry_probe.rs` 可在未来复用已有构建产物，作离线 native registry 检查：它实际加载选定目录并读取构建节点身份且不执行容器，但它是独立进程，不能替代上述 resident 证明，也不因存在源码而视为已运行。B 专用 worker metadata 分支不能直接套到 sensitivity/permutation。

## 旧缓存身份如何失效

源码依据（实际 SHA 在计划内）：`container-plugin/src/loader.rs` 在装载时内联 script_file；`factory.rs` 为该加载定义构造 `PluginIdentity`，包含原始 manifest 字节 SHA、实际脚本 SHA、完整 image reference；`dag-core/src/fingerprint.rs` 的 v3 执行指纹将这些值纳入，同时纳入 engine/source revision、node/spec 和输入身份。

因此重新加载候选后，manifest SHA 和 image reference 都变化，受影响方法节点重新计算的缓存键应变化，依赖链通过上游指纹继续传播。typed 自身 manifest/script/image 不变；若其输入的上游执行身份变化，下游键仍可随链传播。当前 resident 在内存保留旧加载定义时不会因磁盘补丁自动获得新身份；只有实际装载核对后才能确认迁移。以上是源码机制说明，**未做活体缓存失效实验**；不删除旧缓存，不声称已有指纹即完成实际失效。方法已验范围、接口/隔离 DAG、实际部署、科研资格分别核算；迁移候选不授予 G0、研究资格或科学发布。
