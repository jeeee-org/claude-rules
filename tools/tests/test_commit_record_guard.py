"""hooks/commit-record-guard.sh のテスト。

exit 0 = 通す（fail-openを含む）／exit 2 = 止めて差し戻す。
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'hooks' / 'commit-record-guard.sh'


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_hook(command, cwd, tool_name='Bash'):
    payload = json.dumps({
        'tool_name': tool_name,
        'tool_input': {'command': command},
        'cwd': str(cwd),
    })
    return subprocess.run(['bash', str(HOOK)], input=payload, text=True,
                          capture_output=True)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, 'init', '-b', 'main')
        git(self.repo, 'config', 'user.email', 't@example.com')
        git(self.repo, 'config', 'user.name', 'test')
        (self.repo / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        (self.repo / 'checkpoints').mkdir()
        (self.repo / 'checkpoints' / '2026-01-01-初期構成-立ち上げ.md').write_text('# ログ\n', encoding='utf-8')
        (self.repo / 'app.py').write_text('x = 1\n', encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', '初期')

    def tearDown(self):
        self.tmp.cleanup()

    def touch(self, rel, text='変更\n'):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    # --- 止める ---

    def test_記録が無いcommitは止まる(self):
        self.touch('app.py', 'x = 2\n')
        r = run_hook('git commit -am "直した"', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('記録の関門', r.stderr)

    def test_addとcommitを繋いでも止まる(self):
        self.touch('app.py', 'x = 2\n')
        r = run_hook('git add -A && git commit -q -F -', self.repo)
        self.assertEqual(r.returncode, 2)

    def test_メッセージ本文が記録に触れていても止まる(self):
        self.touch('app.py', 'x = 2\n')
        r = run_hook("git commit -F - <<'EOF'\nPROGRESS.mdは次で書く\nEOF", self.repo)
        self.assertEqual(r.returncode, 2)

    def test_cdで別のリポを指しても見る先が変わる(self):
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(other)]))
        git(other, 'init', '-b', 'main')
        git(other, 'config', 'user.email', 't@example.com')
        git(other, 'config', 'user.name', 'test')
        (other / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        git(other, 'add', '-A')
        git(other, 'commit', '-m', '初期')
        (other / 'app.py').write_text('x = 1\n', encoding='utf-8')
        # 実行元は記録を書き終えたリポでも、commitするのは別のリポ
        self.touch('PROGRESS.md', '# 進捗\n更新\n')
        r = run_hook(f'cd {other} && git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 2)

    # --- 通す ---

    def test_checkpointを足していれば通る(self):
        self.touch('app.py', 'x = 2\n')
        self.touch('checkpoints/2026-01-02-不具合対応-切り分け.md', '# ログ\n')
        r = run_hook('git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_日本語のパスのcheckpointでも通る(self):
        self.touch('app.py', 'x = 2\n')
        self.touch('checkpoints/2026-01-02-記録の関門-フックの追加.md', '# ログ\n')
        r = run_hook('git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_PROGRESSを直していれば通る(self):
        self.touch('app.py', 'x = 2\n')
        self.touch('PROGRESS.md', '# 進捗\n更新\n')
        r = run_hook('git commit -am x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_モノレポの下の記録でも通る(self):
        self.touch('tasks/a/app.py', 'x = 2\n')
        self.touch('tasks/a/checkpoints/2026-01-02-移行-取り込み.md', '# ログ\n')
        r = run_hook('git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_通す指定があれば通る(self):
        self.touch('app.py', 'x = 2\n')
        r = run_hook('CR_SKIP_RECORD_GUARD=1 git commit -am x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_amendとdry_runは対象外(self):
        self.touch('app.py', 'x = 2\n')
        for cmd in ('git commit --amend --no-edit', 'git commit --dry-run -am x'):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 0)

    def test_commitでないコマンドは見ない(self):
        self.touch('app.py', 'x = 2\n')
        for cmd in ('git status', 'git log --grep commit', 'echo "git commit"',
                    'git add -A'):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 0)

    def test_Bash以外のツールは見ない(self):
        self.touch('app.py', 'x = 2\n')
        r = run_hook('git commit -am x', self.repo, tool_name='Edit')
        self.assertEqual(r.returncode, 0)

    def test_gitの外では黙る(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_hook('git commit -am x', d).returncode, 0)

    def test_記録の方式を使っていないリポでは黙る(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d)
            git(plain, 'init', '-b', 'main')
            git(plain, 'config', 'user.email', 't@example.com')
            git(plain, 'config', 'user.name', 'test')
            (plain / 'app.py').write_text('x = 1\n', encoding='utf-8')
            git(plain, 'add', '-A')
            git(plain, 'commit', '-m', '初期')
            (plain / 'app.py').write_text('x = 2\n', encoding='utf-8')
            self.assertEqual(run_hook('git commit -am x', plain).returncode, 0)

    def test_変更が何も無ければ黙る(self):
        self.assertEqual(run_hook('git commit -am x', self.repo).returncode, 0)


if __name__ == '__main__':
    unittest.main()
