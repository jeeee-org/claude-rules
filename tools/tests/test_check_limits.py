import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-limits.sh"


class CheckLimitsRulesTest(unittest.TestCase):
    """rules/ の下の常時ロードされる分を測る（2026-09-30）。"""

    def run_check(self, cc, pj, **env):
        e = dict(os.environ, CLAUDE_CONFIG_DIR=str(cc), CODEX_HOME=str(cc / "codex"), **env)
        return subprocess.run(["bash", str(SCRIPT), str(pj)], capture_output=True, text=True, env=e)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cc = root / "cc"
        self.pj = root / "pj"
        (self.cc / "rules" / "sub").mkdir(parents=True)
        (self.pj / ".claude" / "rules").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_global_rules_sum_unconditional_only(self):
        (self.cc / "rules" / "a.md").write_text("x" * 100)
        (self.cc / "rules" / "sub" / "b.md").write_text("---\ndescription: d\n---\n" + "y" * 50)
        (self.cc / "rules" / "c.md").write_text("---\npaths:\n  - src/**\n---\n" + "z" * 5000)
        r = self.run_check(self.cc, self.pj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = next(l for l in r.stdout.splitlines() if "（常時・2件）" in l)
        self.assertIn(str(100 + len("---\ndescription: d\n---\n") + 50) + "B", line)
        self.assertIn("paths指定あり 1件", r.stdout)

    def test_global_rules_over_limit_fails(self):
        (self.cc / "rules" / "big.md").write_text("x" * 200)
        r = self.run_check(self.cc, self.pj, CR_LIMIT_GLOBAL="100")
        self.assertEqual(r.returncode, 1)
        self.assertIn("超過", r.stdout)

    def test_pj_rules_measured_against_pj_limit(self):
        (self.pj / ".claude" / "rules" / "r.md").write_text("x" * 300)
        r = self.run_check(self.cc, self.pj, CR_LIMIT_PJ="200")
        self.assertEqual(r.returncode, 1)
        self.assertIn(".claude/rules/*.md（常時・1件）", r.stdout)

    def test_no_rules_dir_prints_nothing(self):
        (self.cc / "rules" / "sub").rmdir()
        (self.cc / "rules").rmdir()
        r = self.run_check(self.cc, self.pj)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("rules/*.md", r.stdout)


if __name__ == "__main__":
    unittest.main()
