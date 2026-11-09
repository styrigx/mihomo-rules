import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import (RuleError, dedup_cidrs, dedup_domains, load_sources, norm_cidr,  # noqa: E402
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


class Repo(unittest.TestCase):
    def test_sources_and_own(self):
        cfg = load_sources()
        self.assertEqual(len(cfg["sets"]), 13)
        for s in cfg["sets"]:
            f = own_file(s)
            if f.exists():
                norm = norm_domain if s["kind"] == "geosite" else norm_cidr
                for e in read_payload(f):
                    norm(e, str(f))
        names = {(s["kind"], s["name"]) for s in cfg["sets"]}
        self.assertIn(("geosite", "galaxy-store"), names)

    def test_own_counts(self):
        root = Path(__file__).resolve().parent.parent / "geosite"
        self.assertEqual(len(read_payload(root / "samsung.yaml")), 15)
        self.assertEqual(len(read_payload(root / "galaxy-store.yaml")), 5)


if __name__ == "__main__":
    unittest.main()
