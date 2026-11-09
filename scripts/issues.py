#!/usr/bin/env python3
"""按 build/status.json 维护滚动 issue：每个规则集最多一个打开的 issue。

- 失败：按标题找打开的 issue，有就追加评论，没有就新开。
- 恢复（本次成功发布了新版本）：给打开的 issue 评论"已恢复"并关闭。
- 整体终检没过（什么都没发布）：另有一个「release 终检」issue，规则同上。
环境变量：GITHUB_TOKEN、GITHUB_REPOSITORY、可选 RUN_URL。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from common import BUILD, log

API = "https://api.github.com"
TITLE = "规则集构建失败：{}"
DIST_KEY = "release 终检"


def gh(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "styrigx-mihomo-rules",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r) if r.length != 0 else None


def open_issues(repo: str) -> dict[str, dict]:
    out, page = {}, 1
    while True:
        items = gh("GET", f"/repos/{repo}/issues?state=open&per_page=100&page={page}")
        for it in items:
            if "pull_request" not in it:
                out.setdefault(it["title"], it)
        if len(items) < 100:
            return out
        page += 1


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ.get("RUN_URL", "")
    status = json.loads((BUILD / "status.json").read_text(encoding="utf-8"))
    issues = open_issues(repo)
    rc = 0

    def fail(key: str, text: str) -> None:
        title = TITLE.format(key)
        body = f"{text}\n\n运行：{run}" if run else text
        it = issues.get(title)
        if it:
            gh("POST", f"/repos/{repo}/issues/{it['number']}/comments", {"body": "仍然失败。\n\n" + body})
            log(f"评论 #{it['number']} {title}")
        else:
            it = gh("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
            log(f"新开 #{it['number']} {title}")

    def recover(key: str) -> None:
        it = issues.get(TITLE.format(key))
        if it:
            gh("POST", f"/repos/{repo}/issues/{it['number']}/comments",
               {"body": f"已恢复，本次发布了新版本。{run}".strip()})
            gh("PATCH", f"/repos/{repo}/issues/{it['number']}", {"state": "closed", "state_reason": "completed"})
            log(f"关闭 #{it['number']}")

    try:
        for sid, st in status["sets"].items():
            if st["ok"] and status["final_ok"]:
                recover(sid)
            elif not st["ok"]:
                kept = {"stale": "release 里保留了上次好的版本。",
                        "missing": "release 里没有这个规则集的旧版本，本次缺这一份。"}.get(st.get("state"), "")
                fail(sid, f"规则集 `{sid}`（{st['provider']}）本次没有发布新版本。{kept}\n\n```\n{st.get('error', '')[:3000]}\n```")
        if status["final_ok"]:
            recover(DIST_KEY)
        else:
            fail(DIST_KEY, "组装好的成品 没通过终检（mihomo -t / 加载检查），本次没有发布，release 分支保持不变。详见运行日志。")
    except urllib.error.HTTPError as e:
        log(f"GitHub API 出错：{e.code} {e.read()[:500]!r}")
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
