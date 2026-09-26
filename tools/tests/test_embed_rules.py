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
        # 初回は個人の運用の選択が必須。テストでは明示しない限り「なし」で書き込む
        if '--options' not in args and '--remove' not in args and '--check' not in args \
                and not (self.pj / 'AGENTS.md').exists() and not (self.pj / 'CLAUDE.md').exists():
            args = (*args, '--options', 'none')
        return self.run_raw(str(self.pj), *args)

    def run_raw(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=self.env)

    def read(self, name):
        return (self.pj / name).read_text(encoding='utf-8')

    def test_両方向けはAGENTSに統一しCLAUDEを作らない(self):
        p = self.run_tool()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.read('AGENTS.md').startswith(BEGIN))
        self.assertIn('embed-both', self.read('AGENTS.md').splitlines()[0])
        self.assertFalse((self.pj / 'CLAUDE.md').exists())
        self.assertTrue(os.access(self.pj / '.claude-rules' / 'check-limits.sh', os.X_OK))

    def test_PJ固有の指示は残り共通ルールの下に続く(self):
        (self.pj / 'AGENTS.md').write_text('# PJ\n\n- 固有の指示\n', encoding='utf-8')
        self.run_tool('--options', 'none')
        text = self.read('AGENTS.md')
        self.assertLess(text.index('claude-rules:embed:end'), text.index('- 固有の指示'))
        self.assertTrue(text.endswith('# PJ\n\n- 固有の指示\n'))

    def test_2回目は変更なしで最新と判定(self):
        self.run_tool()
        before = self.read('AGENTS.md')
        p = self.run_tool()
        self.assertIn('変更なし', p.stdout)
        self.assertEqual(before, self.read('AGENTS.md'))
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
        p = self.run_tool('--options', 'none')
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

    def test_CLAUDEをAGENTSへ移して統一する(self):
        (self.pj / 'CLAUDE.md').write_text(
            '# CLAUDE.md — demo\n\nこのファイルはClaude Codeへのプロジェクト指示書。\n'
            '共通の進行管理・Git・記録ルールはグローバル`~/.claude/CLAUDE.md`に従う。\n\n'
            '## Git運用（グローバル§5の差分）\n- 上限はグローバル既定どおり（PJ CLAUDE.md 6KB）\n'
            '- グローバルホットキーは使わない\n- CLAUDE.local.mdは個人用\n- CLAUDE.mdを読む前に何かする\n',
            encoding='utf-8')
        (self.pj / 'AGENTS.md').write_text('<!-- BEGIN:x -->\n既存\n<!-- END:x -->\n', encoding='utf-8')
        p = self.run_tool('--options', 'all', '--absorb-claude-md')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.pj / 'CLAUDE.md').exists())
        text = self.read('AGENTS.md')
        own = text[text.index('claude-rules:embed:end'):]
        self.assertIn('# AGENTS.md — demo', own)
        self.assertIn('Claude Code / Codexへのプロジェクト指示書', own)
        self.assertIn('このファイル先頭の共通ルールに従う', own)
        self.assertIn('## Git運用（共通ルール§5の差分）', own)
        self.assertIn('共通ルールの既定どおり（PJ AGENTS.md 6KB）', own)
        self.assertIn('グローバルホットキー', own)
        self.assertLess(own.index('# AGENTS.md — demo'), own.index('既存'))
        # 機械で直さなかった行だけを行番号付きで出す（CLAUDE.local.md とホットキーは出さない）
        self.assertIn('CLAUDE.mdを読む前に何かする', p.stderr)
        self.assertNotIn('CLAUDE.local.md', p.stderr)
        self.assertNotIn('ホットキー', p.stderr)

    def test_移す指定は両方向けだけ(self):
        (self.pj / 'CLAUDE.md').write_text('# x\n', encoding='utf-8')
        p = self.run_tool('--target', 'claude', '--options', 'none', '--absorb-claude-md')
        self.assertEqual(p.returncode, 2)

    def test_配下のPJの状態の一覧(self):
        root = self.pj.parent
        for name in ('a', 'b', 'c'):
            (root / name).mkdir()
            (root / name / '.git').mkdir()
        (root / 'b' / 'CLAUDE.md').write_text('# b\n', encoding='utf-8')
        subprocess.run([sys.executable, str(TOOL), str(root / 'c'), '--options', 'autopush'],
                       capture_output=True, text=True, env=self.env)
        p = self.run_raw('--scan', str(root))
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = {l.split()[0]: l for l in p.stdout.splitlines()}
        self.assertIn('未書き込み', lines['a'])
        self.assertIn('CLAUDE.mdあり', lines['b'])
        self.assertIn('最新（both / 選択 autopush）', lines['c'])

    def test_グローバルにもあるPCでは二重に読まれると知らせる(self):
        home = Path(self.env['CLAUDE_CONFIG_DIR'])
        home.mkdir()
        (home / 'CLAUDE.md').write_text('<!-- claude-rules:begin -->\n<!-- claude-rules:end -->\n', encoding='utf-8')
        p = self.run_tool('--target', 'claude')
        self.assertIn('二重に読まれます', p.stderr)

    def test_取り除くと元に戻る(self):
        (self.pj / 'CLAUDE.md').write_text('# CLAUDE.md\n\n- 固有\n', encoding='utf-8')
        self.run_tool('--options', 'none')
        self.assertIn('@AGENTS.md', self.read('CLAUDE.md'))
        self.run_tool('--remove')
        self.assertEqual(self.read('CLAUDE.md'), '# CLAUDE.md\n\n- 固有\n')
        self.assertFalse((self.pj / 'AGENTS.md').exists())
        self.assertFalse((self.pj / '.claude-rules').exists())

    def test_上限の判定はブロックの内と外を分けて測る(self):
        (self.pj / 'AGENTS.md').write_text('- 固有\n', encoding='utf-8')
        self.run_tool('--target', 'codex', '--options', 'none')
        p = subprocess.run(['bash', str(self.pj / '.claude-rules' / 'check-limits.sh'), str(self.pj)],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn('AGENTS.md（共通ルール）', p.stdout)
        self.assertRegex(p.stdout, r'AGENTS.md（PJ固有）\s+10B')


    def test_初回に個人の運用を選ばないと止まり一覧を出す(self):
        p = self.run_raw(str(self.pj))
        self.assertEqual(p.returncode, 2)
        self.assertIn('--options', p.stderr)
        self.assertIn('autopush', p.stderr)
        self.assertFalse((self.pj / 'AGENTS.md').exists())

    def test_知らない運用の名前は止まる(self):
        p = self.run_raw(str(self.pj), '--options', 'autopush,nosuch')
        self.assertEqual(p.returncode, 2)
        self.assertIn('nosuch', p.stderr)

    def test_選んだ運用だけが入り必須の決まりは常に入る(self):
        self.run_tool('--options', 'autopush')
        text = self.read('AGENTS.md')
        self.assertIn('選択 autopush。', text.splitlines()[0])
        self.assertIn('**pushは既定で自動**', text)
        self.assertIn('commitはユーザーの指示で行う', text)
        self.assertNotIn('### 5.1 worktreeルール', text)
        self.assertNotIn('禁止①', text)
        self.assertNotIn('push先は§5.1', text)
        for must in ('subjectは日本語50字目安', 'ファイルベースmemory', '禁止②', '## 8. 外部に出す文面', '## 9. 応答の書き方'):
            self.assertIn(must, text)

    def test_何も選ばないと代わりの決まりが入る(self):
        self.run_tool('--options', 'none')
        text = self.read('AGENTS.md')
        self.assertIn('選択 なし。', text.splitlines()[0])
        self.assertIn('pushはユーザーの指示があった時だけ', text)
        self.assertNotIn('pushは既定で自動', text)
        self.assertIn('**§5.2は全PJ必須**', text)

    def test_2回目は前回の選択と書き込み先を引き継ぐ(self):
        self.run_tool('--target', 'codex', '--options', 'worktree,toolname')
        stale = self.read('AGENTS.md').replace('## 9. 応答の書き方', '## 9. 古い')
        (self.pj / 'AGENTS.md').write_text(stale, encoding='utf-8')
        p = self.run_raw(str(self.pj))
        self.assertEqual(p.returncode, 0, p.stderr)
        head = self.read('AGENTS.md').splitlines()[0]
        self.assertIn('embed-codex', head)
        self.assertIn('選択 worktree,toolname。', head)
        self.assertIn('## 9. 応答の書き方', self.read('AGENTS.md'))

    def test_版の境目の空白が詰められても前回の選択を読める(self):
        self.run_tool('--target', 'codex', '--options', 'autopush,worktree')
        text = self.read('AGENTS.md')
        head = text.splitlines()[0]
        squashed = head.replace('(版 ', '(版').replace('選択 ', '選択')
        (self.pj / 'AGENTS.md').write_text(text.replace(head, squashed), encoding='utf-8')
        p = self.run_raw(str(self.pj))
        self.assertEqual(p.returncode, 0, p.stderr)
        new_head = self.read('AGENTS.md').splitlines()[0]
        self.assertIn('embed-codex', new_head)
        self.assertIn('選択 autopush,worktree。', new_head)
        self.assertIn('(版 ', new_head)  # 書き直すと元の形に戻る

    def test_選び直すと入れ替わる(self):
        self.run_tool('--options', 'all')
        self.assertIn('### 5.1 worktreeルール', self.read('AGENTS.md'))
        self.run_tool('--options', 'none')
        self.assertNotIn('### 5.1 worktreeルール', self.read('AGENTS.md'))
        self.assertEqual(self.read('AGENTS.md').count(BEGIN), 1)

    def test_選べる運用の一覧(self):
        p = self.run_raw('--list-options')
        self.assertEqual(p.returncode, 0)
        for name in ('autocommit', 'autopush', 'worktree', 'toolname', '常に入るもの'):
            self.assertIn(name, p.stdout)


if __name__ == '__main__':
    unittest.main()
