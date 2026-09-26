"""tools/build-rules.pyのテスト（共通ルールの正本から読み手ごとの版を作る）。

  python3 -m unittest discover -s tools/tests
"""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'build-rules.py'
_spec = importlib.util.spec_from_file_location('build_rules', TOOL)
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)

GLOBAL_LIMIT = 14336


class ConditionTest(unittest.TestCase):
    def test_条件の書き方(self):
        f = {'claude', 'global'}
        self.assertTrue(br.holds('claude', f))
        self.assertFalse(br.holds('codex', f))
        self.assertTrue(br.holds('codex,claude', f))
        self.assertTrue(br.holds('claude+global', f))
        self.assertFalse(br.holds('claude+embed', f))
        self.assertTrue(br.holds('!embed', f))
        self.assertFalse(br.holds('!global', f))

    def test_行ブロックと行中の条件と語の置き換え(self):
        src = ('<!-- if:codex -->\n消える\n<!-- endif -->\n'
               '<!-- if:claude -->\n残る\n<!-- endif -->\n'
               'A<!-- if:embed -->x<!-- endif -->B {{PJ}}\n')
        self.assertEqual(br.render('claude-global', src), '残る\nAB CLAUDE.md\n')

    def test_値の無い語は止まる(self):
        with self.assertRaises(KeyError):
            br.render('embed-both', '{{INIT}}\n')

    def test_閉じていない条件は止まる(self):
        with self.assertRaises(ValueError):
            br.render('claude-global', '<!-- if:claude -->\nあ\n')


class VariantTest(unittest.TestCase):
    def test_どの版にも仕掛けが残らない(self):
        for v in br.VARIANTS:
            text = br.render(v)
            self.assertNotIn('{{', text, v)
            self.assertNotIn('<!-- if:', text, v)
            self.assertNotIn('<!-- endif', text, v)

    def test_版ごとに指す先が違う(self):
        c = br.render('claude-global')
        self.assertIn('`/init-rules`', c)
        self.assertIn('~/.claude/tools/check-limits.sh', c)
        self.assertIn('push-attribution-guard.sh', c)
        self.assertNotIn('Codexの個人メモリ', c)
        x = br.render('codex-global')
        self.assertIn('`$init-rules`', x)
        self.assertIn('~/.codex/tools/check-limits.sh', x)
        self.assertNotIn('~/.claude/', x)
        self.assertIn('| `AGENTS.md` | PJ固有の指示', x)

    def test_書き込み用は相手のホームにある物を指さない(self):
        for v in ('embed-claude', 'embed-codex', 'embed-both'):
            t = br.render(v)
            self.assertNotIn('~/.claude/tools', t, v)
            self.assertNotIn('~/.codex/tools', t, v)
            self.assertNotIn('init-rules', t, v)
            self.assertNotIn('push-attribution-guard', t, v)
            self.assertIn('.claude-rules/check-limits.sh', t, v)
        both = br.render('embed-both')
        self.assertIn('@AGENTS.md', both)
        self.assertIn('Codexの個人メモリ', both)
        self.assertIn('ファイルベースmemory', both)

    def test_グローバル版は上限に収まる(self):
        for v in br.GLOBAL_OUTPUTS:
            self.assertLessEqual(len(br.global_file(v).encode()), GLOBAL_LIMIT, v)

    def test_書き込み版も同じ上限に収まる(self):
        # PJへ書き込んだブロックは check-limits.sh がグローバルの上限で測る。マーカー行の分を見込む
        for v in ('embed-claude', 'embed-codex', 'embed-both'):
            self.assertLessEqual(len(br.render(v).encode()) + 400, GLOBAL_LIMIT, v)

    def test_コミット済みの生成物が正本と揃っている(self):
        p = subprocess.run([sys.executable, str(TOOL), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_生成物のマーカーはinstallが探す名前(self):
        self.assertTrue(br.global_file('claude-global').startswith('<!-- claude-rules:begin'))
        self.assertTrue(br.global_file('claude-global').endswith('<!-- claude-rules:end -->\n'))
        self.assertTrue(br.global_file('codex-global').startswith('<!-- codex-rules:begin'))


if __name__ == '__main__':
    unittest.main()
