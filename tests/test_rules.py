import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import (RuleError, apply_exclude, dedup_cidrs, dedup_domains, load_sources, norm_cidr,  # noqa: E402
                    norm_domain, own_file, parse_upstream, read_payload)


class Domain(unittest.TestCase):
    def test_classical_convert(self):
        self.assertEqual(norm_domain("DOMAIN-SUFFIX,Samsung.com", "t"), "+.samsung.com")
        self.assertEqual(norm_domain("DOMAIN,a.samsung.com", "t"), "a.samsung.com")
        self.assertEqual(norm_domain("'+.x.com'", "t"), "+.x.com")

    def test_unconvertible_is_error(self):
        for bad in ("DOMAIN-KEYWORD,samsung", "DOMAIN-REGEX,^a.*$", "IP-CIDR,1.1.1.0/24", "^samsung\\.com$", "sam sung.com"):
            with self.assertRaises(RuleError, msg=bad):
                norm_domain(bad, "t")

    def test_dedup_parent(self):
        out, covered = dedup_domains(["+.samsung.com", "a.samsung.com", "+.b.samsung.com", "samsung.com",
                                      "+.samsung.com", "x.org", ".y.samsung.com"])
        self.assertEqual(sorted(out), ["+.samsung.com", "x.org"])
        self.assertEqual(covered, 4)

    def test_no_false_parent(self):
        out, _ = dedup_domains(["+.amsung.com", "samsung.com"])
        self.assertEqual(sorted(out), ["+.amsung.com", "samsung.com"])


class Upstream(unittest.TestCase):
    LINES = ["DOMAIN-SUFFIX,google.com", "DOMAIN,a.b.com", "DOMAIN-KEYWORD,google", "DOMAIN-REGEX,^x$",
             "PROCESS-NAME,com.google.android.gm", "IP-CIDR,8.8.8.0/24,no-resolve", "IP-CIDR6,2001:4860::/32", "+.x.org"]

    def test_classical_domain_skips_counted(self):
        out, skipped = parse_upstream(self.LINES, "geosite", "classical")
        self.assertEqual(out, ["+.google.com", "a.b.com", "+.x.org"])
        self.assertEqual(skipped, {"DOMAIN-KEYWORD": 1, "DOMAIN-REGEX": 1, "PROCESS-NAME": 1, "IP-CIDR": 1, "IP-CIDR6": 1})

    def test_classical_ip(self):
        out, skipped = parse_upstream(self.LINES, "geoip", "classical")
        self.assertEqual(out, ["8.8.8.0/24", "2001:4860::/32"])
        self.assertEqual(sum(skipped.values()), 6)

    def test_payload_invalid_skipped_not_error(self):
        out, skipped = parse_upstream(["+.a.com", "regexp:^a$", "b.com"], "geosite", "payload")
        self.assertEqual(out, ["+.a.com", "b.com"])
        self.assertEqual(skipped, {"INVALID": 1})


class Cidr(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm_cidr("IP-CIDR,10.1.2.3/8,no-resolve", "t"), "10.0.0.0/8")
        self.assertEqual(norm_cidr("2001:DB8::/32", "t"), "2001:db8::/32")
        with self.assertRaises(RuleError):
            norm_cidr("GEOIP,CN", "t")

    def test_dedup(self):
        out, covered = dedup_cidrs(["10.0.0.0/8", "10.1.0.0/16", "10.0.0.0/8", "192.168.0.0/16", "fc00::/7", "fd00::/8"])
        self.assertEqual(out, ["10.0.0.0/8", "192.168.0.0/16", "fc00::/7"])
        self.assertEqual(covered, 2)


class Exclude(unittest.TestCase):
    def test_apply_exclude(self):
        out, n = apply_exclude(
            ["+.amazon.com", "+.amazonaws.com", "s3.amazonaws.com", "+.aws.com", "example.org"],
            ["amazonaws.com", "aws.com"])
        self.assertEqual(sorted(out), ["+.amazon.com", "example.org"])
        self.assertEqual(n, 3)

    def test_apply_exclude_label_boundary(self):
        # 后缀匹配按标签边界算：fakeamazonaws.com 不是 amazonaws.com 的子域
        out, n = apply_exclude(["+.fakeamazonaws.com", "+.x.amazonaws.com"], ["amazonaws.com"])
        self.assertEqual(out, ["+.fakeamazonaws.com"])
        self.assertEqual(n, 1)

    def test_apply_exclude_plus_form(self):
        # exclude 里 `+.x` 与 `x` 都按裸域名算
        out, n = apply_exclude(["+.amazonaws.com", "+.amazon.com"], ["+.amazonaws.com"])
        self.assertEqual(out, ["+.amazon.com"])
        self.assertEqual(n, 1)

    def test_load_sources_normalizes_exclude(self):
        src = ("repos:\n"
               "  metacubex: { repo: MetaCubeX/meta-rules-dat, branch: meta }\n"
               "sets:\n"
               "  - { name: amazon, kind: geosite, provider: Amazon_mrs,\n"
               "      upstream: [{ repo: metacubex, path: \"geo/geosite/amazon.yaml\", format: payload }],\n"
               "      exclude: [\"+.amazonaws.com\", \"aws.com\", \"amazonaws.com\"] }\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sources.yaml"
            p.write_text(src, encoding="utf-8")
            cfg = load_sources(p)
        amz = cfg["sets"][0]
        self.assertEqual(amz["exclude"], ["amazonaws.com", "aws.com"])

    def test_load_sources_exclude_geoip_rejected(self):
        src = ("repos: {}\n"
               "sets:\n"
               "  - { name: cn, kind: geoip, provider: IP_CN_mrs, upstream: [], exclude: [\"amazonaws.com\"] }\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sources.yaml"
            p.write_text(src, encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_sources(p)


class Repo(unittest.TestCase):
    def test_sources_and_own(self):
        cfg = load_sources()
        self.assertEqual(len(cfg["sets"]), 14)
        for s in cfg["sets"]:
            f = own_file(s)
            if f.exists():
                norm = norm_domain if s["kind"] == "geosite" else norm_cidr
                for e in read_payload(f):
                    norm(e, str(f))
        names = {(s["kind"], s["name"]) for s in cfg["sets"]}
        self.assertIn(("geosite", "galaxy-store"), names)

    def test_amazon_uses_upstream_with_exclude(self):
        # 亚马逊走官方上游 + exclude，不再把筛过的全量当自有规则留在仓库里
        cfg = load_sources()
        amz = [s for s in cfg["sets"] if (s["kind"], s["name"]) == ("geosite", "amazon")]
        self.assertEqual(len(amz), 1)
        ups = amz[0]["upstream"]
        self.assertEqual(len(ups), 1)
        self.assertEqual((ups[0]["repo"], ups[0]["path"], ups[0]["format"]),
                         ("metacubex", "geo/geosite/amazon.yaml", "payload"))
        self.assertEqual(len(amz[0].get("exclude") or []), 78)
        self.assertFalse(own_file(amz[0]).exists())

    def test_ai_upstreams_and_exclude(self):
        # AI 集：category-ai-!cn + 12 个 per-AI-app 专用分类；国产 AI 域名与素材市场整站排除
        cfg = load_sources()
        ai = [s for s in cfg["sets"] if (s["kind"], s["name"]) == ("geosite", "ai")]
        self.assertEqual(len(ai), 1)
        paths = sorted(u["path"] for u in ai[0]["upstream"])
        self.assertEqual(paths, sorted(
            "geo/geosite/" + n + ".yaml" for n in
            ["category-ai-!cn", "anthropic", "apple-intelligence", "cursor", "github-copilot",
             "google-gemini", "huggingface", "jetbrains-ai", "openai", "perplexity", "poe",
             "windsurf", "xai"]))
        self.assertEqual(ai[0].get("exclude"),
                         ["cici.com", "ciciai.com", "ciciaicdn.com", "coze.com", "dify.ai",
                          "dola.com", "envato-static.com", "envato.com", "envatousercontent.com",
                          "kimi.ai", "manus.im", "manuscdn.com", "marscode.com", "minimax.io",
                          "moonshot.ai", "qoder.com", "tapnow.ai", "themeforest.net", "trae.ai",
                          "tripo3d.ai"])

    def test_google_nintendo_excludes(self):
        cfg = load_sources()
        by_id = {(s["kind"], s["name"]): s for s in cfg["sets"]}
        self.assertEqual(by_id[("geosite", "google")].get("exclude"),
                         ["oasisfeng.com", "txcloud.net"])
        self.assertEqual(by_id[("geosite", "nintendo")].get("exclude"),
                         ["dkr.com", "hackyourconsole.com", "nentindo.net"])

    def test_own_counts(self):
        root = Path(__file__).resolve().parent.parent / "geosite"
        self.assertEqual(len(read_payload(root / "samsung.yaml")), 15)
        self.assertEqual(len(read_payload(root / "galaxy-store.yaml")), 5)


if __name__ == "__main__":
    unittest.main()
