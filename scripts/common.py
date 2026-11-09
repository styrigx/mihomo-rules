"""共用：读清单、解析/规范化规则条目、读写 payload YAML。"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT  # 原料都在仓库根目录：geosite/、geoip/、sources.yaml
BUILD = Path(os.environ.get("BUILD_DIR", ROOT / "build"))

KIND_BEHAVIOR = {"geosite": "domain", "geoip": "ipcidr"}


class RuleError(Exception):
    """规则写法编不进 MRS（如 DOMAIN-KEYWORD / 正则）——硬错误，不静默丢掉。"""


FORMATS = ("payload", "classical")


def load_sources(path: Path | None = None) -> dict:
    # SOURCES_FILE 只给本地试跑用（例如试加一个来源而不改仓里的清单）
    path = path or Path(os.environ.get("SOURCES_FILE", SRC / "sources.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos = data.get("repos") or {}
    seen = set()
    for s in data["sets"]:
        if s["kind"] not in KIND_BEHAVIOR:
            raise SystemExit(f"sources.yaml: {s['name']} 的 kind 只能是 geosite/geoip")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s["name"]):
            raise SystemExit(f"sources.yaml: 基础名 {s['name']!r} 须小写、连字符")
        key = (s["kind"], s["name"])
        if key in seen:
            raise SystemExit(f"sources.yaml: 重复的规则集 {key}")
        seen.add(key)
        ups = s.get("upstream") or []
        for u in ups:
            if u.get("format", "payload") not in FORMATS:
                raise SystemExit(f"sources.yaml: {set_id(s)} 的 format 只能是 {FORMATS}")
            u.setdefault("format", "payload")
            if "url" in u:
                u["key"] = u["url"]
            elif u.get("repo") in repos and u.get("path"):
                u["key"] = f"{u['repo']}:{u['path']}"
            else:
                raise SystemExit(f"sources.yaml: {set_id(s)} 的来源要么写 url，要么写 repos 里有的 repo + path：{u}")
        s["upstream"] = ups
    data["repos"] = repos
    return data


def set_id(s: dict) -> str:
    return f"{s['kind']}/{s['name']}"


def own_file(s: dict) -> Path:
    return SRC / s["kind"] / f"{s['name']}.yaml"


# ---------- 读取 ----------

def read_payload(path: Path) -> list[str]:
    """读 .yaml（payload: 列表）或 .list（每行一条，# 注释）。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".list" or path.suffix == ".txt":
        out = []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.append(line)
        return out
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict) or "payload" not in data:
        raise RuleError(f"{path}: 缺少 payload: 列表")
    payload = data["payload"] or []
    if not isinstance(payload, list):
        raise RuleError(f"{path}: payload 必须是列表")
    return [str(x).strip() for x in payload if str(x).strip()]


# ---------- 规范化：domain ----------

_DOMAIN_RE = re.compile(r"^(\+\.|\.|\*\.)?([a-z0-9_*-]+)(\.[a-z0-9_*-]+)*$")

def norm_domain(entry: str, where: str) -> str:
    e = entry.strip().strip("'\"").strip()
    if "," in e:
        typ, _, rest = e.partition(",")
        typ = typ.strip().upper()
        val = rest.split(",", 1)[0].strip()
        if typ == "DOMAIN":
            e = val
        elif typ == "DOMAIN-SUFFIX":
            e = "+." + val.lstrip(".")
        else:
            raise RuleError(f"{where}: {entry!r} 是 {typ} 写法，编不进 MRS（domain 只收具体域名），请改写成具体域名")
    e = e.lower().rstrip(".")
    if not e or not _DOMAIN_RE.match(e) or "*" in e.lstrip("*."):
        # 正则、关键字等都会落到这里
        raise RuleError(f"{where}: {entry!r} 不是合法的 domain 条目（正则/关键字编不进 MRS，请改写成具体域名）")
    return e


def _base(d: str) -> str:
    for p in ("+.", "*.", "."):
        if d.startswith(p):
            return d[len(p):]
    return d


def dedup_domains(entries: list[str]) -> tuple[list[str], int]:
    """并集去重，并去掉被某个 `+.父域` 覆盖的条目。返回 (结果, 被父域覆盖而丢掉的条数)。"""
    uniq = list(dict.fromkeys(entries))
    plus = {d[2:] for d in uniq if d.startswith("+.")}
    out, covered = [], 0
    for d in uniq:
        base = _base(d)
        labels = base.split(".")
        # +.x 自身不算被自己覆盖：只看严格的父域；其他写法（x / .x / *.x）看 base 本身及父域
        start = 1 if d.startswith("+.") else 0
        hit = any(".".join(labels[i:]) in plus for i in range(start, len(labels)))
        if hit:
            covered += 1
        else:
            out.append(d)
    return sorted(out, key=lambda d: (list(reversed(_base(d).split("."))), d)), covered


# ---------- 规范化：ipcidr ----------

def norm_cidr(entry: str, where: str) -> str:
    e = entry.strip().strip("'\"").strip()
    if "," in e:
        typ, _, rest = e.partition(",")
        typ = typ.strip().upper()
        if typ not in ("IP-CIDR", "IP-CIDR6"):
            raise RuleError(f"{where}: {entry!r} 是 {typ} 写法，ipcidr 规则集只收 IP-CIDR/IP-CIDR6")
        e = rest.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_network(e, strict=False))
    except ValueError:
        raise RuleError(f"{where}: {entry!r} 不是合法的 CIDR")


def dedup_cidrs(entries: list[str]) -> tuple[list[str], int]:
    nets = {ipaddress.ip_network(x) for x in entries}
    keyset = {(n.version, int(n.network_address), n.prefixlen) for n in nets}
    out, covered = [], 0
    for n in nets:
        inside = False
        for plen in range(0, n.prefixlen):
            sup = n.supernet(new_prefix=plen)
            if (sup.version, int(sup.network_address), plen) in keyset:
                inside = True
                break
        if inside:
            covered += 1
        else:
            out.append(n)
    out.sort(key=lambda n: (n.version, int(n.network_address), n.prefixlen))
    return [str(n) for n in out], covered


# ---------- 上游：宽松解析（跳过并计数，不报错） ----------

_DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX"}
_IP_TYPES = {"IP-CIDR", "IP-CIDR6"}


def parse_upstream(entries: list[str], kind: str, fmt: str) -> tuple[list[str], dict[str, int]]:
    """公开来源：能转的转，编不进 MRS 的行跳过并按类型计数（DOMAIN-KEYWORD、DOMAIN-REGEX、PROCESS-NAME、
    domain 规则集里的 IP 行 / ipcidr 规则集里的域名行、写法不合法的行）。"""
    out: list[str] = []
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    keep = _DOMAIN_TYPES if kind == "geosite" else _IP_TYPES
    norm = norm_domain if kind == "geosite" else norm_cidr
    for raw in entries:
        e = raw.strip().strip("'\"").strip()
        if fmt == "classical" and "," in e:
            typ = e.split(",", 1)[0].strip().upper()
            if typ not in keep:
                skip(typ or "INVALID")
                continue
        try:
            out.append(norm(e, "upstream"))
        except RuleError:
            skip("INVALID")
    return out, skipped


# ---------- 写出 ----------

def write_payload(path: Path, entries: list[str], header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {h}" if h else "#" for h in header]
    lines.append("payload:")
    for e in entries:
        lines.append(f"  - '{e}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_payload(path: Path) -> int:
    try:
        return len(read_payload(path))
    except Exception:
        return -1


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
