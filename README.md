# mihomo-rules

[中文](#中文) · [English](#english)

## 中文

给 [Mihomo](https://github.com/MetaCubeX/mihomo) 用的分流规则集：机器人每天把公开规则（首批来源 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)）和本仓手写的补充规则按类别合并、去重，编译成 MRS。每个规则集同时发布两份：

- `.yaml`：明文 `payload:` 列表，能直接看到里面有哪些规则；
- `.mrs`：Mihomo 用的二进制格式。

本仓只放域名 / IP，不放任何密钥、订阅地址或私人数据。

### 规则集

| 规则集 | behavior | 文件（dist 分支） | rule-provider 名 | 公开来源 | 本仓补充 |
|---|---|---|---|---|---|
| overseas | domain | `geosite/overseas` | `Overseas_mrs` | geolocation-!cn | — |
| cn | domain | `geosite/cn` | `CN_mrs` | cn | — |
| cn | ipcidr | `geoip/cn` | `IP_CN_mrs` | geoip cn | — |
| ai | domain | `geosite/ai` | `AI_mrs` | category-ai-!cn | — |
| google | domain | `geosite/google` | `Google_mrs` | google | — |
| google | ipcidr | `geoip/google` | `IP_Google_mrs` | geoip google | — |
| samsung | domain | `geosite/samsung` | `Samsung_mrs` | samsung | 15 条 |
| galaxy-store | domain | `geosite/galaxy-store` | `Galaxy_Store_mrs` | — | 5 条 |
| nintendo | domain | `geosite/nintendo` | `Nintendo_mrs` | nintendo | — |
| private | domain | `geosite/private` | `Private_mrs` | private | — |
| private | ipcidr | `geoip/private` | `IP_Private_mrs` | geoip private | — |
| ntp | domain | `geosite/ntp` | `NTP_mrs` | category-ntp | — |
| ads | domain | `geosite/ads` | `Ads_mrs` | category-ads-all | — |

每次发布的条目数、来源 commit、跳过的行等写在 dist 分支的 [`manifest.json`](https://github.com/styrigx/mihomo-rules/blob/dist/manifest.json)。

### 怎么用

rule-provider 用 `type: http`、`format: mrs`、`interval: 86400`、`proxy: DIRECT`：

```yaml
rule-providers:
  Samsung_mrs:
    type: http
    behavior: domain
    format: mrs
    interval: 86400
    proxy: DIRECT
    path: ./rules/geosite/samsung.mrs
    url: "https://proxy-rules.styrigx.com/styrigx/mihomo-rules/dist/geosite/samsung.mrs"
  IP_CN_mrs:
    type: http
    behavior: ipcidr
    format: mrs
    interval: 86400
    proxy: DIRECT
    path: ./rules/geoip/cn.mrs
    url: "https://proxy-rules.styrigx.com/styrigx/mihomo-rules/dist/geoip/cn.mrs"
```

完整示例（13 个 rule-provider + 写死的规则顺序）见 [`examples/config.yaml`](examples/config.yaml)。规则顺序：局域网 / 广告先处理，然后 **Galaxy Store → Samsung → AI → Google → … → Overseas → CN**。Galaxy Store 有几条域名也在 samsung 里（如 `+.samsungapps.com`），靠顺序让它先进 Galaxy Store 组。

地址说明：

- `proxy-rules.styrigx.com` 是现有的 styrigx-proxy-rules 中转 Worker，路径 = `/<仓库>/<分支>/<文件>`（和 GitHub raw 布局一致）。**让 Worker 白名单放行本仓 dist 路径是另一个 PR（在 styrigx/styrigx-space），不在本仓。** 放行之前上面的地址会 404。
- 直连 GitHub：`https://raw.githubusercontent.com/styrigx/mihomo-rules/dist/geosite/samsung.mrs`（优先用 raw，jsDelivr 的分支缓存会滞后）。

### 仓库结构

```
main 分支
├── src/
│   ├── own/geosite/      # 手写域名规则（behavior: domain），文件名 = 规则集基础名
│   ├── own/geoip/        # 手写 IP 规则（behavior: ipcidr）
│   └── sources.yaml      # 规则集清单 + 公开来源
├── scripts/              # fetch.py 拉取 · merge.py 合并去重 · build.py 编译自检组装 · issues.py 滚动 issue
├── tests/                # 单元测试
├── examples/config.yaml  # 示例配置
└── .github/workflows/build.yml

dist 分支（机器人生成，每次重建成单个提交强推，不手改、不从它开分支）
├── geosite/<名字>.yaml / .mrs
├── geoip/<名字>.yaml / .mrs
└── manifest.json
```

### 改规则

- **加手写规则**：改 `src/own/geosite/<规则集>.yaml`（IP 放 `src/own/geoip/`），走 PR。推荐写法 `+.example.com`（含子域）或 `example.com`（仅本域）；classical 的 `DOMAIN-SUFFIX,x` / `DOMAIN,x` 会自动转换。`DOMAIN-KEYWORD`、正则等编不进 MRS，会直接报错，请改写成具体域名。
- **加公开来源 / 新规则集**：改 `src/sources.yaml`。一个规则集可以有多个来源，每个来源标 `format`：`payload`（MetaCubeX 那种明文）或 `classical`（`DOMAIN-SUFFIX,x` 这类写法，如 blackmatrix7/ios_rule_script）。公开来源里编不进 MRS 的行（`DOMAIN-KEYWORD`、`DOMAIN-REGEX`、`PROCESS-NAME`、类型不对的行等）跳过并计数，写进 manifest 的 `skipped`，不报错。
- 合并规则：并集去重；被 `+.父域` 覆盖的条目、被更大网段覆盖的网段会去掉。

### 流水线

`.github/workflows/build.yml`：

- 触发：每天 03:17 UTC（北京时间 11:17，上游通常 01:00–02:00 UTC 前后发布）；main 上 `src/`、`scripts/` 有改动；手动 `workflow_dispatch`（勾 `force` 可跳过骤降检查）。PR 只跑检查不发布。
- 步骤：拉取（上游固定到同一个 commit）→ 合并 → `mihomo convert-ruleset` 编译 → 自检 → 发布。
- 自检：编译成功；条目数比当前 dist 骤降不超过 30%（`force` 跳过）；起一个只监听 127.0.0.1 的 mihomo 真加载全部 `.mrs`，加载条数必须等于 YAML 条数；`mihomo -t` 通过。mihomo 二进制固定版本并校验 sha256。
- 某个规则集失败：该规则集保留 dist 里上次好的版本，并开一个滚动 issue（标题「规则集构建失败：<kind>/<name>」，再失败就在同一个 issue 里评论，恢复后自动关闭）；job 标红。
- 发布：dist 内容没变就不推；变了就重建成单个孤儿提交 `git push --force` 到 dist。

### 本地运行

```sh
pip install pyyaml
python -m unittest discover -s tests
python scripts/fetch.py && python scripts/merge.py
python scripts/build.py --mihomo /path/to/mihomo --out /tmp/dist [--prev /path/to/old-dist] [--force]
```

### 许可与来源

本仓以 [GPL-3.0](LICENSE) 发布，与上游一致。公开规则来自 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)（GPL-3.0，其数据又来自 [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat)、[v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) 等，同为 GPL-3.0 / MIT 等开源许可）。dist 里每个 YAML 头部和 `manifest.json` 都写明了来源仓库与 commit。

---

## English

Rule sets for [Mihomo](https://github.com/MetaCubeX/mihomo). A daily GitHub Actions job merges public rules (initially from [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)) with hand-written additions in this repo, per category, deduplicates them and compiles them to MRS. Every set is published twice on the `dist` branch: a plain `.yaml` (`payload:` list, human-readable) and a `.mrs` (binary, for Mihomo). Domains and IPs only — no secrets, subscription URLs or private data.

**Sets** — see the table above: 10 domain sets under `geosite/` and 3 ipcidr sets under `geoip/`. Rule-provider names: `<Category>_mrs` for domains, `IP_<Category>_mrs` for IPs. `manifest.json` on `dist` records counts, upstream commits and skipped lines.

**Usage** — `type: http`, `format: mrs`, `interval: 86400`, `proxy: DIRECT`, url `https://proxy-rules.styrigx.com/styrigx/mihomo-rules/dist/<geosite|geoip>/<name>.mrs` (the existing styrigx-proxy-rules Worker; whitelisting this repo's dist path is a separate PR in styrigx/styrigx-space and those URLs 404 until it lands) or directly `https://raw.githubusercontent.com/styrigx/mihomo-rules/dist/<geosite|geoip>/<name>.mrs`. A full example with the fixed rule order (LAN / ads first, then Galaxy Store → Samsung → AI → Google → … → Overseas → CN) is in [`examples/config.yaml`](examples/config.yaml).

**Editing** — own rules live in `src/own/<geosite|geoip>/<set>.yaml` (`+.example.com` / `example.com`; classical `DOMAIN-SUFFIX`/`DOMAIN` are converted; `DOMAIN-KEYWORD` and regex are a hard error). Sources live in `src/sources.yaml`; a set may have several upstream sources, each with `format: payload` (MetaCubeX plain text) or `format: classical` (Clash classical, e.g. blackmatrix7/ios_rule_script). Upstream lines that cannot go into MRS are skipped and counted in the manifest, not treated as errors. Changes go through pull requests.

**Pipeline** — daily at 03:17 UTC, on pushes to `main` touching `src/` or `scripts/`, and on manual dispatch (`force` skips the >30% drop check). Checks: compile succeeds, entry count does not drop >30% against current `dist`, a real Mihomo instance (pinned version, sha256-verified) loads every `.mrs` with the same entry count as its YAML, and `mihomo -t` passes. A failing set keeps its last good files and gets one rolling issue (commented on repeat failures, closed on recovery). `dist` is rebuilt as a single orphan commit and force-pushed only when content changed.

**License** — [GPL-3.0](LICENSE), same as upstream. Public rules come from MetaCubeX/meta-rules-dat (GPL-3.0), which builds on Loyalsoldier/v2ray-rules-dat and v2fly/domain-list-community; each dist YAML header and `manifest.json` name the source repo and commit.
