# mihomo-rules

[中文](#中文) · [English](#english)

## 中文

给 [Mihomo](https://github.com/MetaCubeX/mihomo) 用的分流规则集。机器人每天把公开规则（首批来源 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)）和本仓手写的补充规则按类别合并、去重，编译成 MRS。只放域名 / IP，不放任何密钥、订阅地址或私人数据。

> **main 是原料，release 是成品。** main 只有手写规则和来源清单；合并后的 `geosite/`、`geoip/` 和 `manifest.json` 都在 release 分支，别在 main 里找成品。

### rule-set

- mihomo：[release branch](https://github.com/styrigx/mihomo-rules/tree/release)
  - 域名规则：[geosite/](https://github.com/styrigx/mihomo-rules/tree/release/geosite)
  - IP 规则：[geoip/](https://github.com/styrigx/mihomo-rules/tree/release/geoip)
  - 发布记录：[manifest.json](https://github.com/styrigx/mihomo-rules/blob/release/manifest.json)（条目数、来源 commit、跳过的行）

每个规则集发两份：`.yaml` 是明文 `payload:` 列表，能直接看内容；`.mrs` 是 Mihomo 用的二进制。

### GeoSite（域名，behavior: domain）

| 规则集 | rule-provider 名 | 公开来源 | 本仓补充 | 下载 |
|---|---|---|---|---|
| `overseas` | `Overseas_mrs` | `geosite:geolocation-!cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/overseas.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/overseas.mrs) |
| `cn` | `CN_mrs` | `geosite:cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/cn.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/cn.mrs) |
| `ai` | `AI_mrs` | `geosite:category-ai-!cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ai.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ai.mrs) |
| `google` | `Google_mrs` | `geosite:google` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/google.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/google.mrs) |
| `samsung` | `Samsung_mrs` | `geosite:samsung` | 15 条 | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/samsung.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/samsung.mrs) |
| `galaxy-store` | `Galaxy_Store_mrs` | — | 5 条 | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/galaxy-store.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/galaxy-store.mrs) |
| `nintendo` | `Nintendo_mrs` | `geosite:nintendo` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/nintendo.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/nintendo.mrs) |
| `private` | `Private_mrs` | `geosite:private` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/private.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/private.mrs) |
| `ntp` | `NTP_mrs` | `geosite:category-ntp` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ntp.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ntp.mrs) |
| `ads` | `Ads_mrs` | `geosite:category-ads-all` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ads.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ads.mrs) |

### GeoIP（IP，behavior: ipcidr）

| 规则集 | rule-provider 名 | 公开来源 | 本仓补充 | 下载 |
|---|---|---|---|---|
| `cn` | `IP_CN_mrs` | `geoip:cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/cn.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/cn.mrs) |
| `google` | `IP_Google_mrs` | `geoip:google` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/google.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/google.mrs) |
| `private` | `IP_Private_mrs` | `geoip:private` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/private.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/private.mrs) |

命名：域名规则集是 `<类别>_mrs`，IP 规则集是 `IP_<类别>_mrs`。

### 怎么用

rule-provider 用 `type: http`、`format: mrs`、`interval: 86400`、`proxy: DIRECT`，地址用 GitHub raw（jsDelivr 的分支缓存会滞后），也可以换成自己的中转：

```yaml
rule-providers:
  Samsung_mrs:
    type: http
    behavior: domain
    format: mrs
    interval: 86400
    proxy: DIRECT
    path: ./rules/geosite/samsung.mrs
    url: "https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/samsung.mrs"
  IP_CN_mrs:
    type: http
    behavior: ipcidr
    format: mrs
    interval: 86400
    proxy: DIRECT
    path: ./rules/geoip/cn.mrs
    url: "https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/cn.mrs"
```

完整示例（13 个 rule-provider + 写死的规则顺序）见 [`examples/config.yaml`](examples/config.yaml)。规则顺序：局域网 / 广告先处理，然后 **Galaxy Store → Samsung → AI → Google → … → Overseas → CN**。Galaxy Store 有几条域名也在 samsung 里（如 `+.samsungapps.com`），靠顺序让它先进 Galaxy Store 组。

### 仓库结构

main 和 release 用同一套文件夹：`geosite/` 放域名规则，`geoip/` 放 IP 规则。

```
main 分支（原料）
├── geosite/              # 手写域名规则，文件名 = 规则集基础名
├── geoip/                # 手写 IP 规则（暂无）
├── sources.yaml          # 规则集清单 + 公开来源
├── scripts/              # fetch.py 拉取 · merge.py 合并去重 · build.py 编译自检组装 · issues.py 滚动 issue
├── tests/
├── examples/config.yaml
└── .github/workflows/build.yml

release 分支（成品，机器人每次重建成单个提交强推，不手改、不从它开分支）
├── geosite/<名字>.yaml / .mrs
├── geoip/<名字>.yaml / .mrs
└── manifest.json
```

main 的 [`geosite/samsung.yaml`](geosite/samsung.yaml) 只有 15 条手写补充；release 同路径的成品是合并公开来源后的全集。

### 改规则

- **加手写规则**：改 `geosite/<规则集>.yaml`（IP 放 `geoip/`），走 PR。推荐写法 `+.example.com`（含子域）或 `example.com`（仅本域）；classical 的 `DOMAIN-SUFFIX,x` / `DOMAIN,x` 会自动转换。`DOMAIN-KEYWORD`、正则等编不进 MRS，会直接报错。
- **加公开来源 / 新规则集**：改 `sources.yaml`。一个规则集可以有多个来源，每个来源标 `format`：`payload`（MetaCubeX 那种明文）或 `classical`（如 blackmatrix7/ios_rule_script）。公开来源里编不进 MRS 的行跳过并计数，写进 manifest 的 `skipped`。
- 合并规则：并集去重；被 `+.父域` 覆盖的条目、被更大网段覆盖的网段会去掉。

### 流水线

`.github/workflows/build.yml`：

- 触发：每天 03:17 UTC（北京时间 11:17）；main 上 `geosite/`、`geoip/`、`sources.yaml`、`scripts/` 有改动；手动 `workflow_dispatch`（勾 `force` 跳过骤降检查）。PR 只跑检查不发布。
- 步骤：拉取（上游固定到同一个 commit）→ 合并 → `mihomo convert-ruleset` 编译 → 自检 → 发布到 release。
- 自检：编译成功；条目数比当前 release 骤降不超过 30%；起一个只监听 127.0.0.1 的 mihomo 真加载全部 `.mrs`，加载条数必须等于 YAML 条数；`mihomo -t` 通过。mihomo 固定版本并校验 sha256。
- 某个规则集失败：保留 release 里上次好的版本，开一个滚动 issue（再失败就评论，恢复后自动关闭）；job 标红。
- 发布：内容没变就不推；变了就重建成单个孤儿提交强推到 release。

### 本地运行

```sh
pip install pyyaml
python -m unittest discover -s tests
python scripts/fetch.py && python scripts/merge.py
python scripts/build.py --mihomo /path/to/mihomo --out /tmp/out [--prev /path/to/old-release] [--force]
```

### 许可与来源

[GPL-3.0](LICENSE)，与上游一致。公开规则来自 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)（GPL-3.0，其数据又来自 [Loyalsoldier/v2ray-rules-dat](https://github.com/Loyalsoldier/v2ray-rules-dat)、[v2fly/domain-list-community](https://github.com/v2fly/domain-list-community) 等）。release 里每个 YAML 头部和 `manifest.json` 都写明来源仓库与 commit。

---

## English

Rule sets for [Mihomo](https://github.com/MetaCubeX/mihomo). A daily job merges public rules (initially [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)) with hand-written additions, deduplicates them and compiles them to MRS. Domains and IPs only.

> **`main` is the source, `release` is the output.** Merged `geosite/`, `geoip/` and `manifest.json` live on the `release` branch only.

### rule-set

- mihomo: [release branch](https://github.com/styrigx/mihomo-rules/tree/release) · [geosite/](https://github.com/styrigx/mihomo-rules/tree/release/geosite) · [geoip/](https://github.com/styrigx/mihomo-rules/tree/release/geoip) · [manifest.json](https://github.com/styrigx/mihomo-rules/blob/release/manifest.json)

### GeoSite (behavior: domain)

| Set | rule-provider | Upstream | Own | Download |
|---|---|---|---|---|
| `overseas` | `Overseas_mrs` | `geosite:geolocation-!cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/overseas.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/overseas.mrs) |
| `cn` | `CN_mrs` | `geosite:cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/cn.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/cn.mrs) |
| `ai` | `AI_mrs` | `geosite:category-ai-!cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ai.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ai.mrs) |
| `google` | `Google_mrs` | `geosite:google` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/google.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/google.mrs) |
| `samsung` | `Samsung_mrs` | `geosite:samsung` | 15 | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/samsung.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/samsung.mrs) |
| `galaxy-store` | `Galaxy_Store_mrs` | — | 5 | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/galaxy-store.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/galaxy-store.mrs) |
| `nintendo` | `Nintendo_mrs` | `geosite:nintendo` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/nintendo.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/nintendo.mrs) |
| `private` | `Private_mrs` | `geosite:private` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/private.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/private.mrs) |
| `ntp` | `NTP_mrs` | `geosite:category-ntp` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ntp.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ntp.mrs) |
| `ads` | `Ads_mrs` | `geosite:category-ads-all` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geosite/ads.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geosite/ads.mrs) |

### GeoIP (behavior: ipcidr)

| Set | rule-provider | Upstream | Own | Download |
|---|---|---|---|---|
| `cn` | `IP_CN_mrs` | `geoip:cn` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/cn.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/cn.mrs) |
| `google` | `IP_Google_mrs` | `geoip:google` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/google.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/google.mrs) |
| `private` | `IP_Private_mrs` | `geoip:private` | — | [yaml](https://github.com/styrigx/mihomo-rules/blob/release/geoip/private.yaml) · [mrs](https://raw.githubusercontent.com/styrigx/mihomo-rules/release/geoip/private.mrs) |

**Usage** — `type: http`, `format: mrs`, `interval: 86400`, `proxy: DIRECT`, url `https://raw.githubusercontent.com/styrigx/mihomo-rules/release/<geosite|geoip>/<name>.mrs` (or your own mirror). Full example with the fixed rule order: [`examples/config.yaml`](examples/config.yaml).

**Editing** — own rules in `geosite/<set>.yaml` / `geoip/<set>.yaml` on `main`; sources in `sources.yaml`. `DOMAIN-KEYWORD` and regex are a hard error; upstream lines that cannot go into MRS are skipped and counted. Changes go through pull requests.

**Pipeline** — daily at 03:17 UTC, on pushes to `main` touching rules, `sources.yaml` or `scripts/`, and on manual dispatch. Compile, >30% drop check, real Mihomo load check and `mihomo -t` must pass; `release` is rebuilt as a single orphan commit only when content changed.

**License** — [GPL-3.0](LICENSE), same as upstream.
