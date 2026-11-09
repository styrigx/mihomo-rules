#!/usr/bin/env python3
"""拉取：把 sources.yaml 列出的上游文件下到 build/upstream/。

repos 里的每个仓库先解析成一个固定 commit（git ls-remote），该仓库的文件都按这个 commit 下载，
保证同一次构建内容一致；写 url: 的来源直接下载（不固定 commit）。
单个文件失败只记到 build/fetch.json 的 errors，由 merge.py 判定用到它的规则集失败、保留上次好的版本。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.parse
import urllib.request

from common import BUILD, load_sources, log, set_id

UA = "styrigx-mihomo-rules/1.0 (+https://github.com/styrigx/mihomo-rules)"


def resolve_commit(repo: str, branch: str) -> str:
    out = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.split()
    if not out:
        raise RuntimeError(f"上游 {repo}@{branch} 找不到")
    return out[0]


def download(url: str, tries: int = 3) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def main() -> None:
    cfg = load_sources()
    dest = BUILD / "upstream"
    dest.mkdir(parents=True, exist_ok=True)
    result = {"repos": {}, "files": {}, "errors": {}}
    for name, r in cfg["repos"].items():
        try:
            commit = resolve_commit(r["repo"], r["branch"])
            result["repos"][name] = {**r, "commit": commit}
            log(f"上游 {name} = {r['repo']}@{r['branch']} {commit}")
        except Exception as e:  # noqa: BLE001
            result["repos"][name] = {**r, "commit": None, "error": str(e)}
            log(f"上游 {name} 解析失败：{e}")
    for s in cfg["sets"]:
        for u in s["upstream"]:
            key = u["key"]
            if key in result["files"] or key in result["errors"]:
                continue
            if "url" in u:
                url, label = u["url"], u["url"]
            else:
                rp = result["repos"][u["repo"]]
                if not rp["commit"]:
                    result["errors"][key] = rp.get("error", "上游仓库解析失败")
                    continue
                url = f"https://raw.githubusercontent.com/{rp['repo']}/{rp['commit']}/" + urllib.parse.quote(u["path"])
                label = f"{rp['repo']}@{rp['commit'][:12]}:{u['path']}"
            try:
                body = download(url)
                suffix = "." + (u.get("path") or urllib.parse.urlparse(url).path).rsplit(".", 1)[-1]
                local = dest / (hashlib.sha1(key.encode()).hexdigest()[:16] + suffix)
                local.write_bytes(body)
                result["files"][key] = {"local": str(local), "bytes": len(body), "label": label}
                log(f"  ok  {label} ({len(body)} B)")
            except Exception as e:  # noqa: BLE001
                result["errors"][key] = str(e)
                log(f"  ERR {label}: {e}  (影响 {set_id(s)})")
    (BUILD / "fetch.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
