#!/usr/bin/env python3
"""合并：按规则集把公开来源（可多个）+ 自有规则取并集、去重，写成 build/merged/<kind>/<name>.yaml（payload: 列表）。

- 公开来源 format: payload（MetaCubeX 明文）或 classical（DOMAIN-SUFFIX,x 这类 Clash classical 写法）。
  DOMAIN / DOMAIN-SUFFIX、IP-CIDR / IP-CIDR6 自动转；编不进 MRS 的行（DOMAIN-KEYWORD、DOMAIN-REGEX、
  PROCESS-NAME、不合法的行等）跳过并按类型计数（merge.json / manifest 的 skipped），不报错。
- 自有规则（geosite/**、geoip/**）：classical 的 DOMAIN / DOMAIN-SUFFIX 也自动转；DOMAIN-KEYWORD、正则等是硬错误
  （整个命令退出码 2，改自有规则的 PR 会直接红），不静默丢掉。
- 去重：完全相同的去掉；被某个 `+.父域` 覆盖的条目去掉（有 +.samsung.com 就不要 a.samsung.com）；
  ipcidr 规范成网段写法，被更大网段覆盖的去掉。
- 公开来源拉取失败：只让用到它的规则集失败，build.py 保留上次好的版本。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import (BUILD, ROOT, RuleError, dedup_cidrs, dedup_domains, load_sources, log, norm_cidr,
                    norm_domain, own_file, parse_upstream, read_payload, set_id, write_payload)


def main() -> int:
    cfg = load_sources()
    fetch = json.loads((BUILD / "fetch.json").read_text(encoding="utf-8"))
    report: dict[str, dict] = {}
    own_errors: list[str] = []

    for s in cfg["sets"]:
        sid = set_id(s)
        dedup = dedup_domains if s["kind"] == "geosite" else dedup_cidrs
        r: dict = {"ok": False, "own": None, "sources": []}
        try:
            up: list[str] = []
            skipped_all: dict[str, int] = {}
            for u in s["upstream"]:
                key = u["key"]
                if key in fetch["errors"]:
                    raise RuleError(f"上游拉取失败 {key}: {fetch['errors'][key]}")
                f = fetch["files"][key]
                got, skipped = parse_upstream(read_payload(Path(f["local"])), s["kind"], u["format"])
                if not got:
                    raise RuleError(f"上游 {f['label']} 解析后一条可用规则都没有（跳过 {skipped}）")
                up += got
                for k, v in skipped.items():
                    skipped_all[k] = skipped_all.get(k, 0) + v
                r["sources"].append({"source": f["label"], "format": u["format"], "count": len(set(got)),
                                     **({"skipped": skipped} if skipped else {})})
                if skipped:
                    log(f"  !   {sid} ← {f['label']}: 跳过 {skipped}")
            own: list[str] = []
            of = own_file(s)
            if of.exists():
                r["own"] = str(of.relative_to(ROOT))
                norm = norm_domain if s["kind"] == "geosite" else norm_cidr
                try:
                    own = [norm(x, r["own"]) for x in read_payload(of)]
                except RuleError as e:
                    own_errors.append(str(e))
                    raise
            if not up and not own:
                raise RuleError("规则集没有任何来源（upstream 为空且没有自有规则文件）")
            merged, covered = dedup(up + own)
            up_set, own_set = set(up), set(own)
            r.update(
                ok=True,
                upstream_count=len(up_set),
                own_count=len(own_set),
                own_already_upstream=len(own_set & up_set),
                dropped_covered=covered,
                skipped=skipped_all,
                count=len(merged),
            )
            src_line = ", ".join(x["source"] for x in r["sources"]) or "无"
            skip_line = "，".join(f"{k} {v}" for k, v in sorted(skipped_all.items())) or "无"
            header = [
                f"{sid}  (behavior: {'domain' if s['kind'] == 'geosite' else 'ipcidr'})",
                "由 styrigx/mihomo-rules 机器人生成，勿手改；改规则请到 main 分支 geosite/ 或 geoip/。",
                f"公开来源: {src_line}",
                f"自有规则: {r['own'] or '无'}",
                f"条目: {len(merged)}（公开 {len(up_set)} + 自有 {len(own_set)}，重叠 {len(own_set & up_set)}，"
                f"被父域/大网段覆盖去掉 {covered}）",
                f"公开来源里跳过（编不进 MRS）: {skip_line}",
            ]
            write_payload(BUILD / "merged" / s["kind"] / f"{s['name']}.yaml", merged, header)
            log(f"  ok  {sid}: {len(merged)}")
        except (RuleError, KeyError, OSError, ValueError) as e:
            r["error"] = str(e)
            log(f"  ERR {sid}: {e}")
        report[sid] = r

    (BUILD / "merge.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if own_errors:
        log("自有规则有写法错误（硬错误）：\n  " + "\n  ".join(own_errors))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
