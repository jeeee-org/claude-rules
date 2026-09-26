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
        f = {'claude', 'autopush'}
        self.assertTrue(br.holds('claude', f))
        self.assertFalse(br.holds('codex', f))
        self.assertTrue(br.holds('codex,claude', f))
        self.assertTrue(br.holds('claude+autopush', f))
        self.assertFalse(br.holds('claude+codex', f))
        self.assertTrue(br.holds('!worktree', f))
        self.assertFalse(br.holds('!autopush', f))

    def test_行ブロックと行中の条件と語の置き換え(self):
        src = ('<!-- if:codex -->\n消える\n<!-- endif -->\n'
               '<!-- if:claude -->\n残る\n<!-- endif -->\n'
               'A<!-- if:autopush -->x<!-- endif -->B {{PJ}}\n')
        self.assertEqual(br.render('embed-claude', src, options=set()), '残る\nAB CLAUDE.md\n')

    def test_値の無い語は止まる(self):
        with self.assertRaises(KeyError):
            br.render('embed-both', '{{INIT}}\n')

    def test_閉じていない条件は止まる(self):
        with self.assertRaises(ValueError):
            br.render('embed-claude', '<!-- if:claude -->\nあ\n')

    def test_知らない運用は止まる(self):
        with self.assertRaises(KeyError):
            br.render('embed-both', options={'nosuch'})
        with self.assertRaises(ValueError):
            br.parse_options('autopush,nosuch')


class VariantTest(unittest.TestCase):
    def test_どの版と選択にも仕掛けが残らない(self):
        for v in br.VARIANTS:
            for opts in (set(), set(br.OPTIONS)):
                text = br.render(v, options=opts)
                self.assertNotIn('{{', text, v)
                self.assertNotIn('<!-- if:', text, v)
                self.assertNotIn('<!-- endif', text, v)

    def test_版ごとに指す先が違う(self):
        c = br.render('embed-claude')
        self.assertIn('| `CLAUDE.md` | PJ固有の指示', c)
        self.assertNotIn('Codexの個人メモリ', c)
        x = br.render('embed-codex')
        self.assertIn('| `AGENTS.md` | PJ固有の指示', x)
        self.assertIn('`.agents/skills/<name>/SKILL.md`', x)
        self.assertNotIn('ファイルベースmemory', x)
        both = br.render('embed-both')
        self.assertIn('PJに`CLAUDE.md`を作らない', both)
        self.assertIn('Codexの個人メモリ', both)
        self.assertIn('ファイルベースmemory', both)

    def test_相手のホームにある物を指さない(self):
        for v in br.VARIANTS:
            t = br.render(v, options=set(br.OPTIONS))
            self.assertIn('以前の共通ルール', t, v)
            self.assertNotIn('~/.claude/tools', t, v)
            self.assertNotIn('~/.codex/tools', t, v)
            self.assertNotIn('init-rules', t, v)
            self.assertNotIn('push-attribution-guard', t, v)
            self.assertNotIn('グローバル', t, v)
            self.assertIn('.claude-rules/check-limits.sh', t, v)

    def test_上限に収まる(self):
        # PJへ書き込んだブロックは check-limits.sh が14,336Bで測る。マーカー行の分を見込む
        for v in br.VARIANTS:
            self.assertLessEqual(len(br.render(v, options=set(br.OPTIONS)).encode()) + 400, GLOBAL_LIMIT, v)

    def test_標準出力へ出せる(self):
        p = subprocess.run([sys.executable, str(TOOL), '--variant', 'embed-both', '--options', 'none'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('pushはユーザーの指示があった時だけ', p.stdout)


if __name__ == '__main__':
    unittest.main()
