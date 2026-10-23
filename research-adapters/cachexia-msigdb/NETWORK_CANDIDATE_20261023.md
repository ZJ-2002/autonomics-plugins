# MSigDB 节点专属运输候选

2026-10-23，工程候选已验证，尚未部署。离线 GMT 解析沿用既有通过证据；在线生产运输与驻留加载验收为 PENDING。没有重下或重解析完整资源，没有科研或 G0 放行。

## 当前事实

主会话通过现有 gateway metadata reader 只读核查实际 `8765` 端口：`cachexia-msigdb` 为 registered/published、无加载错误，两个 kind 为 `cachexia_msigdb_gmt`、`cachexia_gmt_import`，source rev `3568272020d75be43d004f6b59f47fc9bec2e718`，subdir `research-adapters/cachexia-msigdb`。本任务没有读取凭据或数据库。先前硬编码 `18790` 的连接拒绝不能当作当前服务未启动。

当前 runtime manifest SHA256 为 `8758d87c86c488ebb22100c47686a59dff21155414ac72b0eea0d8e44f12d503`，脚本为 `9224757a039f7c2cd9f0dc2f47cfe70c49ed2b916cc48d14d4cb449ec255d5fa`，与既有完整下载证据一致。镜像仍为 `ghcr.io/zj-2002/biotools-py@sha256:7ad6aeafa87672699d28b61b6bed12fc81fcdbfc43222a0abf17e2d56fb806f5`。

本次受管容器现场 HEAD 对照确认：默认继承路径选中回环代理，抛出 `ProxyError`，HTTP 状态为 `NOT_RECEIVED`；候选节点环境实际进入同一固定镜像后不再选择该域名代理，官方 HEAD 返回 HTTP `200`，Content-Length `48689`。二者均保留 TLS 验证、关闭重定向；响应正文读取量为 0。该长度是响应头，不是新文件长度或完整 SHA 证明。完整文件身份、50 集合与 7322 成员的数值及七端口证据继续复用 `c5487b12939c4776b4ff5187ace5a7aa`，没有由 HEAD 重新证明。

## 最小配置

只在在线节点 `[nodes.command.env]` 增加：

```toml
no_proxy = "data.broadinstitute.org"
NO_PROXY = "data.broadinstitute.org"
```

这是在线节点整个容器内的显式官方域名直连策略。两个拼写都覆盖容器继承的既有例外值，避免 requests 优先采用小写旧值；不会重写宿主或 daemon 环境。节点只接受该固定域名构造的版本资源地址，重定向仍受同一域名、路径和 HTTPS 限制。其他域名仍沿用继承代理。安装前提是该节点允许官方域名直接出站；若生产必须走企业代理，应保留 PENDING 并提供批准的可达运输配置，不自动回退到其他路由。

共享路由器已有 `drop_host_proxy_for_images`，但本节点使用的 biotools-py 被其他节点共用，因此未把该镜像加入全局列表。没有更改共享路由器、daemon 配置、插件 pin、运行时镜像或容器网络模式。离线节点继续 `network=isolated` 且没有新增代理环境。

候选 manifest SHA256：`23a72a892a40aaf802242bf24e818c407409281b311394e7a1020d7efcbb55a8`。`scripts/gmt.py` 字节未改，保留全部 20 键合同、角色/版本/物种/集合/命名空间限制、HTTP 200/完整长度/SHA 检查、失败诊断及七产物发布边界；现有发布安全修复未被覆盖。HEAD 失败诊断是运输 canary 记录，不冒充节点失败产物或成功 GMT。

## 实际执行与证据

受管 session `201edae8b9e149839be0cebbd7be45e2`，状态 CLEANED，worker/launcher exit 0，archive manifest SHA256 `0e6da25e0d1de4c00d1821977aafeb1a551a7d7c1cc7cace9ce1732bbbb45745`。

必要证据成员 `permanent/msigdb-node-network-candidate/verification.json`，SHA256 `a6bf40e93156c96c4a3145a514477e00956d21db3799c93da29559decf573425`。同目录保留源快照、两个逐次 canary JSON、镜像身份及单元测试输出；宿主 plugins.toml、qualified image profile、runtime manifest/脚本及父环境的前后身份一致。两次容器均成功停止并删除，保留受管意图账本，没有独立后台服务。

`test_msigdb_network.py` 两项自清理测试通过，实际覆盖小写/大写/混合代理与缺失/空/既有例外的 9 个 requests 环境组合，验证官方域名无有效代理、TLS 验证开启、其他域仍有代理以及父环境不变。没有重复已有解析、失败传播或统计测试。canary 从候选 TOML 读取 env 并检查实际容器 env，尚未声称经过驻留 loader 执行；主仓当前源码中 `compile/spec_compile.rs`、`compile/render.rs` 到 container-runtime `build_create_args` 保留这些普通环境键。

## 交由主会话的一次部署后小验收

脚本版本须分别记录：原封存中 `prove_network_candidate.py` SHA256 为
`c04eb8390a8be813028f513ac3e077d5a08512827098d73df14df6983bb8a60d`；
其后新增 `--installed`、装载源码身份检查和单次 canary 分支，当前 SHA256 为
`d845c1ec22e48487cb5f9ff1a263d51bb011f06de3a0d5e6bfee9610a714c558`。
这段增量已经静态审阅，但尚未执行，不在原封存的脚本执行证明范围内。
原候选 manifest、GMT 脚本及网络单元测试与封存一致，不因这个脚本增量重复旧验收。

主会话统一审查、发布、pin 和维护部署；本任务不执行这些动作。加载后只读确认 registry 使用新候选 manifest 身份、原 gmt SHA 和固定 image，两个 kind 均注册。然后运行一次：

```sh
python3 -B scripts/research_validation_session.py run -- python-script /home/zj-normal/Work/autonomics-plugins/research-adapters/cachexia-msigdb/prove_network_candidate.py --installed
```

`--installed` 先拒绝 installed runtime 与候选 manifest/gmt 不同的身份，只从 installed manifest 读取节点 env，执行一个固定官方 HEAD，检查实际容器 env、有效代理、原始 HTTP 状态和停止/清理证明；不会重复默认代理反例、下载正文或执行 GMT 解析。运输接纳应要求该次原始 HTTP 为 200，而非仅凭 canary 子进程退出 0（其职责也包括记录网络失败）。此脚本不加载驻留 DAG；registry 源身份/普通 env 经当前 loader 到生产容器的核查须由主会话结合部署记录完成，未执行前保持 PENDING。真实下载只在业务冻结合同需要时执行，继续要求完整文件 SHA/长度及原有 fail-closed 输出合同。
