# 文献检索：Crossref 空字段反例与尚未关闭的字段语义

## 本轮范围

`source_literature` 使用 Rust HTTP 适配器访问作者服务，不属于自行重写科研统计方法。
使用官方服务仍需验证查询翻译、返回身份、失败传播及落盘接口。

本轮检查发现：Crossref 翻译器按原始 `Option` 是否存在判断空检索，而字段内容此前已被
trim 并丢弃空项。因而 `keywords=[" "]`、`authors=[]` 等输入能生成完全没有约束的
`/works` 请求。修复改为检查实际生成的 query、field_queries 和 filters，保留正常的
年份限定检索及含有效词的检索，不为通过测试而禁止这些已有能力。

新增 SDK 回归覆盖七类字段的 127 个非空组合，每个组合检查空数组和纯空白成员两种形式。
这是一个测试内部的 254 个输入，不是 254 个新节点或独立认证。
新增 DAG 回归逐一检查七类空白字段：源节点失败、下游 merge 跳过、两端都不发布输出。
实际构建、反例复现、DAG 运行与归档完成之前，这些新增测试不能称为已通过。

`tools/prove_literature_blank_fields.py` 从确切引擎提交构造两个独立 Git 对象：
先仅加入 SDK 回归验证旧实现确实失败，再加入修复及 DAG 用例。
复用既有编译缓存，在受管 build 会话执行，不修改在用工作区或部署配置。

## 仍未关闭：标题限定不能冒充书目检索

共享 `StructuredSearch.title` 定义为仅限标题，但当前 Crossref 翻译使用
`query.bibliographic`。Crossref 官方说明该查询覆盖标题、作者等书目信息，
并说明旧 `query.title` 已弃用。因此当前转换不能认证为严格的标题限定检索。

- 官方当前 API 入口：https://api.crossref.org/
- 官方历史字段定义及弃用说明：https://github.com/CrossRef/rest-api-doc#field-queries
- 官方书目匹配建议：https://github.com/CrossRef/rest-api-doc/blob/master/api_tips.md

不能把 bibliography 的命中当作 title-only 的同义实现；不能仅按返回标题过滤一页，
再沿用原始 total 或声称完成了标题检索。后续须完整解决检索合同与实际可提供能力的匹配。
本轮不自行更改冻结研究查询，不以空字段修复或测试数量将整条文献节点改为已认证。

## 状态边界

包装器测试、实际 SDK/DAG、官方在线响应、实际部署与合格研究查询是不同证据。
构建准入等待不等于测试失败，也不等于测试通过；其他会话占用配额时不绕过限制。
本轮不授予生产部署或科学放行，不修改 G0、空间零模型或 276/288/696 家族。
