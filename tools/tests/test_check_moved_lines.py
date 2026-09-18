"""tools/check-moved-lines.pyのテスト。

  python3 -m unittest discover -s tools/tests

一時ディレクトリにファイルとgitリポを作り、コマンドとして実行して確かめる。
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'check-moved-lines.py'

SOURCE = """# 学び

## 教訓：完了表示を信用しない

- 件数と容量で独立検証する。

## 確定事項

| 項目 | 内容 |
|------|------|
| 移行元 | 旧サーバ |

---

## 未確定事項
- 旧IPは`192.0.2.10`
"""


class CheckMovedLinesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return str(p)

    def tool(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=cwd)

    def test_all_lines_present_across_targets(self):
        src = self.write('old.md', SOURCE)
        notes = self.write('NOTES.md', '# 学び\n\n## 教訓：完了表示を信用しない\n\n- 件数と容量で独立検証する。\n')
        cp = self.write('checkpoints/2026-06-13-立ち上げ.md', (
            '# 2026-06-13 立ち上げ\n\n## NOTES.md から移設\n\n### 確定事項\n\n'
            '| 項目 | 内容 |\n|---|---|\n| 移行元 | 旧サーバ |\n\n### 未確定事項\n- 旧IPは`192.0.2.10`\n'))
        r = self.tool('--from', src, notes, cp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout, '')
        self.assertIn('どこにも無い行0行', r.stderr)

    def test_reports_missing_lines_with_line_numbers(self):
        src = self.write('old.md', SOURCE)
        notes = self.write('NOTES.md', '# 学び\n\n## 教訓：完了表示を信用しない\n\n## 確定事項\n')
        r = self.tool('--from', src, notes)
        self.assertEqual(r.returncode, 1)
        self.assertIn('    5: - 件数と容量で独立検証する。', r.stdout)
        self.assertIn('   11: | 移行元 | 旧サーバ |', r.stdout)
        self.assertIn('   16: - 旧IPは`192.0.2.10`', r.stdout)
        self.assertNotIn('|------|', r.stdout)  # 表の区切りは数えない
        self.assertNotIn(': ---', r.stdout)      # 水平線も数えない

    def test_demoted_headings_match_unless_strict(self):
        src = self.write('old.md', '## 重大インシデント\n本文\n')
        cp = self.write('cp.md', '### 重大インシデント\n本文\n')
        self.assertEqual(self.tool('--from', src, cp).returncode, 0)
        r = self.tool('--from', src, '--strict-headings', cp)
        self.assertEqual(r.returncode, 1)
        self.assertIn('## 重大インシデント', r.stdout)

    def test_trailing_spaces_are_ignored_but_inner_text_is_exact(self):
        src = self.write('old.md', '- 端末の番号は .59   \n- 旧ルーター\n')
        new = self.write('new.md', '- 端末の番号は .59\n- 旧 ルーター\n')
        r = self.tool('--from', src, new)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), '2: - 旧ルーター')

    def test_indentation_changes_are_ignored(self):
        # 箇条書きの続きの行を、字下げを外して別の節へ移した形（voice-inputの移行で出た）
        src = self.write('old.md', '- [x] 決めた\n  理由の1行目\n    理由の2行目\n- 残す\n')
        new = self.write('new.md', '## 理由\n理由の1行目\n  理由の2行目\n- [x] 決めた\n')
        r = self.tool('--from', src, new)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), '4: - 残す')

    def test_reads_source_from_git_revision_with_japanese_path(self):
        repo = self.root / 'repo'
        repo.mkdir()

        def git(*args):
            subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)

        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'test@example.com')
        git('config', 'user.name', 'test')
        git('config', 'core.quotepath', 'true')  # 既定の挙動を、利用者の設定に左右されず再現する
        (repo / '記録').mkdir()
        (repo / '記録/メモ.md').write_text('# メモ\n- 移す行\n- 消える行\n', encoding='utf-8')
        git('add', '-A')
        git('commit', '-q', '-m', 'fixture')
        (repo / '記録/メモ.md').write_text('# メモ\n', encoding='utf-8')  # 作業ツリーでは書き換え済み
        cp = self.write('cp.md', '- 移す行\n')
        r = self.tool('--from', 'HEAD:記録/メモ.md', '--repo', str(repo), str(repo / '記録/メモ.md'), cp)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(r.stdout.strip(), '3: - 消える行')

    def test_mono_source_is_resolved_from_repo_not_git_root(self):
        """モノレポのタスクで走らせた時、ルート直下の同名ファイルと比べない"""
        repo = self.root / 'mono'
        repo.mkdir()

        def git(*args):
            subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)

        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'test@example.com')
        git('config', 'user.name', 'test')
        (repo / 'REQUIREMENTS.md').write_text('# 本体\n- 本体だけの行\n', encoding='utf-8')
        (repo / 'tasks/x').mkdir(parents=True)
        (repo / 'tasks/x/REQUIREMENTS.md').write_text('# タスク\n- 移す行\n', encoding='utf-8')
        git('add', '-A')
        git('commit', '-q', '-m', 'fixture')
        moved = self.write('moved.md', '# タスク\n- 移す行\n')

        r = self.tool('--from', 'HEAD:REQUIREMENTS.md', '--repo', str(repo / 'tasks/x'), moved)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)      # タスク側と比べている
        self.assertIn('比較元: HEAD:tasks/x/REQUIREMENTS.md', r.stderr)
        self.assertNotIn('本体だけの行', r.stdout)

        # リポルートを指せば本体側。どちらを読んだかは「比較元」で分かる
        r = self.tool('--from', 'HEAD:REQUIREMENTS.md', '--repo', str(repo), moved)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('比較元: HEAD:REQUIREMENTS.md', r.stderr)
        self.assertIn('本体だけの行', r.stdout)

    def test_shows_the_plain_file_it_compared(self):
        src = self.write('old.md', SOURCE)
        r = self.tool('--from', src, src)
        self.assertIn(f'比較元: {src}', r.stderr)

    def test_aborts_on_unreadable_source_or_target(self):
        src = self.write('old.md', SOURCE)
        r = self.tool('--from', str(self.root / 'nothing.md'), src)
        self.assertEqual(r.returncode, 2)
        self.assertIn('中止', r.stderr)
        r = self.tool('--from', src, str(self.root / 'nothing.md'))
        self.assertEqual(r.returncode, 2)
        self.assertIn('移動先', r.stderr)
        r = self.tool('--from', 'HEAD:NOTES.md', '--repo', str(self.root), src)
        self.assertEqual(r.returncode, 2)
        self.assertIn('gitから読めない', r.stderr)


if __name__ == '__main__':
    unittest.main()
