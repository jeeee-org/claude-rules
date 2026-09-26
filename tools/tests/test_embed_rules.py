"""tools/embed-rules.pyのテスト（共通ルールをPJのルールファイルへ書き込む）。

  python3 -m unittest discover -s tools/tests

一時ディレクトリをPJに見立て、コマンドとして実行して確かめる。ホームは一時ディレクトリへ向ける。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
TOOL = TOOLS / 'embed-rules.py'
BEGIN = '<!-- claude-rules:embed:begin'


class EmbedTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.pj = base / 'pj'
        self.pj.mkdir()
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(base / 'claude'), CODEX_HOME=str(base / 'codex'))

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL), str(self.pj), *args],
                              capture_output=True, text=True, env=self.env)

    def read(self, name):
        return (self.pj / name).read_text(encoding='utf-8')

    def test_両方向けは共通ルールをAGENTSへ書きCLAUDEから読み込む(self):
        p = self.run_tool()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.read('AGENTS.md').startswith(BEGIN))
        self.assertIn('embed-both', self.read('AGENTS.md').splitlines()[0])
        self.assertIn('@AGENTS.md', self.read('CLAUDE.md').splitlines())
        self.assertNotIn(BEGIN, self.read('CLAUDE.md'))
        self.assertTrue(os.access(self.pj / '.claude-rules' / 'check-limits.sh', os.X_OK))

    def test_PJ固有の指示は残り共通ルールの下に続く(self):
        (self.pj / 'AGENTS.md').write_text('# PJ\n\n- 固有の指示\n', encoding='utf-8')
        self.run_tool()
        text = self.read('AGENTS.md')
        self.assertLess(text.index('claude-rules:embed:end'), text.index('- 固有の指示'))
        self.assertTrue(text.endswith('# PJ\n\n- 固有の指示\n'))

    def test_2回目は変更なしで最新と判定(self):
        self.run_tool()
        before = self.read('AGENTS.md'), self.read('CLAUDE.md')
        p = self.run_tool()
        self.assertIn('変更なし', p.stdout)
        self.assertEqual(before, (self.read('AGENTS.md'), self.read('CLAUDE.md')))
        self.assertEqual(self.run_tool('--check').returncode, 0)

    def test_古いブロックは差し替わり外は触らない(self):
        self.run_tool()
        stale = self.read('AGENTS.md').replace('## 9. 応答の書き方', '## 9. 古い見出し') + '- 後から足した固有の指示\n'
        (self.pj / 'AGENTS.md').write_text(stale, encoding='utf-8')
        self.assertEqual(self.run_tool('--check').returncode, 1)
        self.run_tool()
        text = self.read('AGENTS.md')
        self.assertIn('## 9. 応答の書き方', text)
        self.assertNotIn('古い見出し', text)
        self.assertIn('- 後から足した固有の指示', text)
        self.assertEqual(text.count(BEGIN), 1)

    def test_既存のCLAUDEは残し読み込みを先頭に足してCodexに届かないと知らせる(self):
        (self.pj / 'CLAUDE.md').write_text('# CLAUDE.md\n\n- Claude向けの固有指示\n', encoding='utf-8')
        p = self.run_tool()
        text = self.read('CLAUDE.md')
        self.assertTrue(text.splitlines()[1] == '@AGENTS.md')
        self.assertIn('- Claude向けの固有指示', text)
        self.assertIn('Codexからは読まれません', p.stderr)

    def test_Claudeだけ向けはCLAUDEへ書きAGENTSを作らない(self):
        p = self.run_tool('--target', 'claude')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.read('CLAUDE.md').startswith(BEGIN))
        self.assertFalse((self.pj / 'AGENTS.md').exists())

    def test_Codexだけ向けはAGENTSへ書きCLAUDEを作らない(self):
        self.run_tool('--target', 'codex')
        self.assertIn('embed-codex', self.read('AGENTS.md').splitlines()[0])
        self.assertFalse((self.pj / 'CLAUDE.md').exists())

    def test_書き換えない指定では何も作らない(self):
        p = self.run_tool('--dry-run')
        self.assertIn('AGENTS.md', p.stdout)
        self.assertEqual(sorted(x.name for x in self.pj.iterdir()), [])

    def test_グローバルにもあるPCでは二重に読まれると知らせる(self):
        home = Path(self.env['CLAUDE_CONFIG_DIR'])
        home.mkdir()
        (home / 'CLAUDE.md').write_text('<!-- claude-rules:begin -->\n<!-- claude-rules:end -->\n', encoding='utf-8')
        p = self.run_tool('--target', 'claude')
        self.assertIn('二重に読まれます', p.stderr)

    def test_取り除くと元に戻る(self):
        (self.pj / 'CLAUDE.md').write_text('# CLAUDE.md\n\n- 固有\n', encoding='utf-8')
        self.run_tool()
        self.run_tool('--remove')
        self.assertEqual(self.read('CLAUDE.md'), '# CLAUDE.md\n\n- 固有\n')
        self.assertFalse((self.pj / 'AGENTS.md').exists())
        self.assertFalse((self.pj / '.claude-rules').exists())

    def test_上限の判定はブロックの内と外を分けて測る(self):
        (self.pj / 'AGENTS.md').write_text('- 固有\n', encoding='utf-8')
        self.run_tool('--target', 'codex')
        p = subprocess.run(['bash', str(self.pj / '.claude-rules' / 'check-limits.sh'), str(self.pj)],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn('AGENTS.md（共通ルール）', p.stdout)
        self.assertRegex(p.stdout, r'AGENTS.md（PJ固有）\s+10B')


if __name__ == '__main__':
    unittest.main()
