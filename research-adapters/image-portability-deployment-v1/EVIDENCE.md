# 测试后交付定位（文档增量）

本文件在候选测试封存后新增；不属于该次受测源码。其余五个文件与永久 candidate-source 副本 SHA 一致。未为补写定位重跑旧测试。

- 实际新增 unittest：10；全部通过，失败 0，错误 0，验证器退出码 0。
- launcher / worker 退出码：0 / 0；session 状态 CLEANED。
- 新增统计方法执行、镜像 pull/build/push、registry 请求、安装、服务控制：均为 0。
- 未产生失败会话；既有失败匿名读取记录仍在原档案，不覆盖。

| 永久记录 | 路径 | SHA-256 |
|---|---|---|
| Session | `/home/zj-normal/.local/state/autonomics/validation-archives/10a405cb13fb408082cf7045dc5c614c/SESSION.json` | `89b3baeac99c3b3553b9ce36934470dc28a93f06d9c6acf94c7db0c2d31060cd` |
| Manifest seal | `/home/zj-normal/.local/state/autonomics/validation-archives/10a405cb13fb408082cf7045dc5c614c/artifacts/MANIFEST.json` | `9a7c1ca77126ff230be7fa2beb347d452747c6a220a518ecaa3c30d8b3a5329f` |
| Verification | `/home/zj-normal/.local/state/autonomics/validation-archives/10a405cb13fb408082cf7045dc5c614c/artifacts/permanent/image-portability-deployment-v1/verification.json` | `5e22effb9da688612504de09cb1c07be7b7fe8a556b74262268240cef6515a12` |

## 源文件基线与当前 SHA

“基线”为编制候选时捕获的实际字节，当前主仓/插件仓还有其它未提交修改；不能用 HEAD 替代这些 SHA。原文件均未被本会话修改。

| 文件 | 基线 SHA = 当前 SHA | 候选应用后 manifest SHA |
|---|---|---|
| `research-adapters/cachexia-sensitivity/manifest.toml` | `bb85e60767b29fa9e897cacac0960d3db317755006095e4d491f2fcf11798c9c` | `05b94997d201e8c598aa1aef445ebb814eec10cd721bf164681bcd2585709730` |
| `research-adapters/cachexia-sensitivity/scripts/sensitivity.R` | `12becb67fb8438a13c574b96443fc0329b7afc782183b5a8e64e92fbac8335fb` | 保留原样 |
| `research-adapters/cachexia-permutation/manifest.toml` | `47ecf4ef550a3ac6c096f51c2b75e118ee03b171e483e7f02d2787a6ee552dfb` | `c6aff3afdcbe27de26dc2f38a8a3e97553aed862ca0f39086736577c5c773598` |
| `research-adapters/cachexia-permutation/scripts/permutation.py` | `4ed7b28998948510f8f9c3d5491afb023282f8cb15f59297f9907484d3f083d8` | 保留原样 |
| `research-adapters/cachexia-sensitivity-typed-values/manifest.toml` | `6211dd45936f71f8a85fb7708bb32ecabd8f9778b3bcdb5f48a81a3ad7fbb538` | 保留原样 |
| `research-adapters/cachexia-sensitivity-typed-values/scripts/typed_values.py` | `7572cf2bf2839d147f3b7d60f4e0bc81adff3dc0fca8d08787f4320f20176b2c` | 保留原样 |

## 受测候选文件 SHA

| 文件 | 测试封存 SHA = 当前 SHA |
|---|---|
| `README.md` | `61ecc54772d618783c33a0576c97eab540af76ecaa6568578a6e7e5cdcb53cb7` |
| `cachexia-permutation.patch` | `614da62f4a6d86f2dd6995bacff52998acf6f84e5c3bf03353fde91e139a6713` |
| `cachexia-sensitivity.patch` | `612a36153b4f4130372507a38f4e65d7f50d2bcbde3160d040d869e89117f790` |
| `migration-plan.json` | `9403e7e755924a530bdd772cb095b848d293cd0bce7c810544a064b6152bf6c8` |
| `validate_candidate.py` | `d2230a3615a61bd2955a5d676e714bd998e9de50991be47ec0c6e9b8d010acd4` |

永久受测源码副本目录：`/home/zj-normal/.local/state/autonomics/validation-archives/10a405cb13fb408082cf7045dc5c614c/artifacts/permanent/image-portability-deployment-v1/candidate-source`。未向候选目录复制私密日志、凭据、原始研究载荷或本地 session 档案。

## 原证据与尚未执行项

原 sensitivity 发布档案 seal：`73211a1190c85644bc564c9264c50ffa3f5cdf67fea16cf88025ed102731d294`；verification SHA：`19c15f73dc762efed3ee4dadef17d4457911959180578aa1a9518ff1a3b541a0`，回读 19 文件。原 permutation seal：`b23e99f1f4af173966267011a4e5580a9c07390adaa1c6a8dc0c722ee7cd0485`；verification SHA：`d2bd100a8d280d86ae8efc98c48ae33850290ea887e8878d8c0c903bad67fa58`，回读 22 文件。源/目标完整镜像映射、实际源代码 SHA、config 与有序 RootFS 摘要在 `migration-plan.json`。

PENDING：匿名公开可读（上次封存读取失败，本次未重查）；主会话发布含两补丁的固定完整 rev；关联 catalog/release-lock 审阅；目标宿主按 digest 的镜像准入与安装；用户统一生产切换；实际 resident 装载身份只读核验。现有 metadata API 的身份字段缺口见 README。活体缓存失效实验未执行，不声称已验证；该项不是本次结构验证的完成条件。科研资格/G0/冻结方案均未更改。
