#!/usr/bin/env python3
"""编译 + 发布前自检 + 组装成品。

用法：build.py --mihomo PATH --out DIR [--prev DIR] [--force]

对每个规则集：
  1. 合并成功（merge.json）
  2. `mihomo convert-ruleset <domain|ipcidr> yaml in.yaml out.mrs` 编译成功
  3. 条目数比上次 release 骤降不超过 30%（--force 跳过这一项）
  4. 真正加载：起一个只监听 127.0.0.1 的 mihomo（file 类型 rule-provider 引用全部 .mrs），
     从 /providers/rules 读每个规则集加载到的条数，必须 > 0 且与 YAML 条数一致
任一项失败：该规则集用 --prev（当前 release 分支）里的上次好版本；没有上次版本就缺这一份。
最后对组装好的成品 整体再跑一遍 `mihomo -t` + 加载检查，不过就不发布（退出码 3）。

产出：--out 目录（geosite/、geoip/、manifest.json）和 build/status.json（给 issues.py 用）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from common import BUILD, KIND_BEHAVIOR, count_payload, load_sources, log, set_id

DROP_LIMIT = 0.30
# 访问本机 external-controller 不走任何 HTTP(S)_PROXY
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def provider_name(s: dict) -> str:
    return s["provider"]


def test_config(sets: list[dict], root: Path, port: int | None) -> str:
    lines = ["mode: rule", "log-level: warning", "geo-auto-update: false",
             "profile: {store-selected: false, store-fake-ip: false}"]
    if port:
        lines.append(f"external-controller: 127.0.0.1:{port}")
    lines.append("rule-providers:")
    for s in sets:
        p = root / s["kind"] / f"{s['name']}.mrs"
        lines.append(f"  {provider_name(s)}: {{type: file, behavior: {KIND_BEHAVIOR[s['kind']]}, format: mrs, path: '{p}'}}")
    lines.append("rules:")
    for s in sets:
        extra = ",no-resolve" if s["kind"] == "geoip" else ""
        lines.append(f"  - RULE-SET,{provider_name(s)},DIRECT{extra}")
    lines.append("  - MATCH,DIRECT")
    return "\n".join(lines) + "\n"


def _env(root: Path) -> dict:
    # mihomo 只允许读 home（-d）下的文件；规则集在别的目录，用 SAFE_PATHS 放行（只读，不往成品里写缓存）
    return {**os.environ, "SAFE_PATHS": str(root.resolve())}


def mihomo_t(mihomo: str, sets: list[dict], root: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "config.yaml"
        cfg.write_text(test_config(sets, root, None), encoding="utf-8")
        r = subprocess.run([mihomo, "-t", "-d", d, "-f", str(cfg)], capture_output=True, text=True, timeout=120,
                           env=_env(root))
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]


def mihomo_load(mihomo: str, sets: list[dict], root: Path) -> dict[str, int]:
    """起 mihomo 真加载一遍，返回 {provider 名: 加载到的条数}。起不来就抛异常。"""
    port = free_port()
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "config.yaml"
        cfg.write_text(test_config(sets, root, port), encoding="utf-8")
        logf = open(Path(d) / "run.log", "w+")
        proc = subprocess.Popen([mihomo, "-d", d, "-f", str(cfg)], stdout=logf, stderr=subprocess.STDOUT,
                                env=_env(root))
        try:
            want = {provider_name(s) for s in sets}
            deadline = time.time() + 60
            last_err = None
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                try:
                    with _LOCAL.open(f"http://127.0.0.1:{port}/providers/rules", timeout=5) as r:
                        data = json.load(r)["providers"]
                    if want <= set(data):
                        return {k: int(v.get("ruleCount", 0)) for k, v in data.items()}
                except Exception as e:  # noqa: BLE001
                    last_err = e
                time.sleep(1)
            logf.seek(0)
            raise RuntimeError(f"mihomo 没起来或没加载完：{last_err}\n{logf.read()[-2000:]}")
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            logf.close()


def prev_counts(prev: Path | None) -> dict[str, int]:
    if not prev or not prev.exists():
        return {}
    m = prev / "manifest.json"
    if m.exists():
        try:
            return {k: v["count"] for k, v in json.loads(m.read_text())["sets"].items() if v.get("count")}
        except Exception:  # noqa: BLE001
            pass
    out = {}
    for y in prev.glob("geo*/*.yaml"):
        out[f"{y.parent.name}/{y.stem}"] = count_payload(y)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--prev", type=Path)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    cfg = load_sources()
    sets = cfg["sets"]
    merge = json.loads((BUILD / "merge.json").read_text(encoding="utf-8"))
    fetch = json.loads((BUILD / "fetch.json").read_text(encoding="utf-8"))
    prev = prev_counts(a.prev)
    stage = BUILD / "compiled"
    shutil.rmtree(stage, ignore_errors=True)
    version = subprocess.run([a.mihomo, "-v"], capture_output=True, text=True).stdout.split("\n")[0].strip()
    log(version)

    status: dict[str, dict] = {}
    for s in sets:
        sid = set_id(s)
        m = merge.get(sid, {})
        st = {"set": sid, "provider": s["provider"], "ok": False}
        status[sid] = st
        if not m.get("ok"):
            st["error"] = "合并失败：" + m.get("error", "未知")
            continue
        src = BUILD / "merged" / s["kind"] / f"{s['name']}.yaml"
        dst = stage / s["kind"] / f"{s['name']}.mrs"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst.with_suffix(".yaml"))
        r = subprocess.run([a.mihomo, "convert-ruleset", KIND_BEHAVIOR[s["kind"]], "yaml", str(src), str(dst)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
            st["error"] = "编译失败：" + (r.stdout + r.stderr)[-1500:]
            continue
        n = m["count"]
        p = prev.get(sid)
        st.update(count=n, prev_count=p)
        if p and p > 0 and n < p * (1 - DROP_LIMIT):
            msg = f"条目数骤降 {p} → {n}（-{(p - n) / p:.0%}，超过 {DROP_LIMIT:.0%}）"
            if a.force:
                st["forced"] = msg
                log(f"  ! {sid}: {msg}，force=true 放行")
            else:
                st["error"] = msg + "；确认无误可手动 workflow_dispatch 勾选 force 强制发布"
                continue
        st["ok"] = True

    # 4. 真加载（只测编译成功的那些）
    cand = [s for s in sets if status[set_id(s)]["ok"]]
    if cand:
        try:
            loaded = mihomo_load(a.mihomo, cand, stage)
        except Exception as e:  # noqa: BLE001
            loaded = None
            log(f"整体加载失败，逐个重测：{e}")
        for s in cand:
            st = status[set_id(s)]
            got = loaded.get(s["provider"]) if loaded is not None else None
            if got is None:
                try:
                    got = mihomo_load(a.mihomo, [s], stage).get(s["provider"], 0)
                except Exception as e:  # noqa: BLE001
                    st.update(ok=False, error=f"mihomo 加载失败：{e}")
                    continue
            st["loaded"] = got
            if got <= 0 or got != st["count"]:
                st.update(ok=False, error=f"mihomo 加载条数 {got} ≠ YAML 条数 {st['count']}")
        ok_t, out_t = mihomo_t(a.mihomo, [s for s in cand if status[set_id(s)]["ok"]], stage)
        if not ok_t:
            log("mihomo -t 失败（新编译的规则集）：\n" + out_t)
            for s in cand:
                if status[set_id(s)]["ok"]:
                    ok1, out1 = mihomo_t(a.mihomo, [s], stage)
                    if not ok1:
                        status[set_id(s)].update(ok=False, error="mihomo -t 失败：" + out1[-1500:])

    # 组装成品
    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    manifest_sets = {}
    published = []
    for s in sets:
        sid = set_id(s)
        st = status[sid]
        (out / s["kind"]).mkdir(exist_ok=True)
        files = [f"{s['name']}.yaml", f"{s['name']}.mrs"]
        if st["ok"]:
            for f in files:
                shutil.copy2(stage / s["kind"] / f, out / s["kind"] / f)
            st["state"] = "fresh"
            entry = {k: merge[sid][k] for k in ("count", "upstream_count", "own_count", "own_already_upstream",
                                                 "dropped_covered", "skipped", "sources", "own")}
        elif a.prev and all((a.prev / s["kind"] / f).exists() for f in files):
            for f in files:
                shutil.copy2(a.prev / s["kind"] / f, out / s["kind"] / f)
            st["state"] = "stale"
            old = {}
            try:
                old = json.loads((a.prev / "manifest.json").read_text())["sets"].get(sid, {})
            except Exception:  # noqa: BLE001
                pass
            entry = {**{k: v for k, v in old.items() if k not in ("state", "error")}, "count": count_payload(out / s["kind"] / files[0])}
        else:
            st["state"] = "missing"
            entry = {}
        entry.update(state=st["state"], provider=s["provider"], behavior=KIND_BEHAVIOR[s["kind"]])
        if st.get("error"):
            entry["error"] = st["error"].splitlines()[0][:300]
        if st["state"] != "missing":
            entry["sha256"] = {f: sha256(out / s["kind"] / f) for f in files}
            published.append(s)
        manifest_sets[sid] = entry
        log(f"  {st['state']:7} {sid}: {entry.get('count', '-')}" + (f"  ← {st['error'].splitlines()[0]}" if st.get("error") else ""))

    # 整体终检：组装好的成品 必须能被 mihomo 加载
    final_ok = True
    if published:
        ok_t, out_t = mihomo_t(a.mihomo, published, out)
        if not ok_t:
            final_ok = False
            log("终检 mihomo -t 失败：\n" + out_t)
        try:
            loaded = mihomo_load(a.mihomo, published, out)
            for s in published:
                want = manifest_sets[set_id(s)]["count"]
                if loaded.get(s["provider"], 0) != want:
                    final_ok = False
                    log(f"终检加载条数不符 {set_id(s)}: {loaded.get(s['provider'])} ≠ {want}")
        except Exception as e:  # noqa: BLE001
            final_ok = False
            log(f"终检加载失败：{e}")
    else:
        final_ok = False

    content_hash = hashlib.sha256(json.dumps({k: v.get("sha256") for k, v in manifest_sets.items()},
                                             sort_keys=True).encode()).hexdigest()
    manifest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"repo": os.environ.get("GITHUB_REPOSITORY", "styrigx/mihomo-rules"),
                   "commit": os.environ.get("GITHUB_SHA") or subprocess.run(
                       ["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None},
        "upstream": fetch["repos"],
        "mihomo": version,
        "forced": bool(a.force),
        "content_hash": content_hash,
        "sets": manifest_sets,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (BUILD / "status.json").write_text(json.dumps({"final_ok": final_ok, "sets": status}, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    if not final_ok:
        log("终检没过：不发布。")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
