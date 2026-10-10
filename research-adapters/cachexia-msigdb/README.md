# 完整 MSigDB 输运与 GMT 解析候选路线

未注册正式部署、未认证、未修改生产 plugins.toml；必须查对应最终封存，不把
目录存在或 unit test 通过当作实际 DAG 已通过。

`cachexia_msigdb_gmt` 输入20键冻结 JSON，实际下载指定官方版本完整集合。
`cachexia_gmt_import` 输入完整 GMT 和同一20键合同，离线解析；离线模式不声称
新下载或独立认证来源。整个集合原样保留，禁止自行选基因集/映射/去重/改 ID。

七个输出依次为全部成员 occurrence TSV、全部集合元数据 TSV、原始 GMT、audit、
非空日志、每次 HTTP attempt 表、技术 resource request 状态表。源集合/成员位置
显式保留，重复成员同时给出 occurrence 与 unique 计数，不推断下游权重或得分。
valid ID 失败落 blocked-request.tsv，正常成员/集合/raw/通过状态不发布。

成员表使用 `set_id/gene_id` 加源集合/成员位置，明确为字符串身份列；不是裸
`gene` 经 DataFrame 自动推断成整数后再 CAST，避免 Entrez 前导零在读入时丢失。

按官方 ASCII GMT 格式：name、description、genes；完整单集合轴唯一，集合名与
成员非空，description 列必须存在但可为空，LF/CRLF/无末尾换行可读。此严格资源合同不冒充所有非标准 GMT/GSEA
Java reader 行为。symbols/entrez flavor 显式冻结；不据此认证 gene ID/同源映射。
版本不是由当前日期或默认参数猜测，预期 SHA/bytes/整个集合轴/成员数必须先冻结。

认证层：工程接口/方案合同/隔离物化 DAG。官方统计方法层 NOT_APPLICABLE，
不是一个统计方法；来源与数据格式一致仍须官方完整下载和独立全文解析复审。
不是 ORA/GSEA、签名选择、表达评分、真实队列资格、正式部署/全局资源/恢复/G0。
