"""hooks/push-record-guard.sh のテスト — 記録の関門の本丸（pushの直前に見る）。

commitは既にあるので、コマンドの書き方によらず正確に判定できる。
exit 0 = 通す（fail-openを含む）／exit 2 = 止めて差し戻す。
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'hooks' / 'push-record-guard.sh'


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          capture_output=True, text=True)


def run_hook(command, cwd, tool_name='Bash'):
    payload = json.dumps({'tool_name': tool_name, 'tool_input': {'command': command},
                          'cwd': str(cwd)})
    return subprocess.run(['bash', str(HOOK)], input=payload, text=True, capture_output=True)


class PushGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin = root / 'origin.git'
        self.repo = root / 'work'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.origin)], check=True)
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.repo)],
                       check=True, capture_output=True)
        git(self.repo, 'config', 'user.email', 't@example.com')
        git(self.repo, 'config', 'user.name', 'test')
        (self.repo / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        (self.repo / 'checkpoints').mkdir()
        (self.repo / 'checkpoints' / '2026-01-01-初期構成-立ち上げ.md').write_text('# ログ\n', encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', '初期')
        git(self.repo, 'push', '-q', '-u', 'origin', 'main')

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, message='作業', text='x\n'):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', message)

    # --- 止める ---

    def test_記録の無いcommitを押そうとすると止まる(self):
        self.commit('app.py', 'コードを直した')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('コードを直した', r.stderr)       # どのcommitかを名指しする
        self.assertIn('記録なし:', r.stderr)            # 例外の書き方を案内する

    def test_書き方によらず判定できる(self):
        """commitは既にあるので、呼び出しの形に左右されない（入口との違い）"""
        self.commit('app.py', 'コードを直した')
        for cmd in ('git push', f'cd {self.repo} && git push',
                    f'git -C {self.repo} push origin main',
                    "cat >> a.md <<'EOF'\n追記\nEOF\ngit push"):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 2, cmd)

    def test_記録のあるcommitと無いcommitが混ざっていたら止まる(self):
        self.commit('checkpoints/2026-01-02-対応-記録.md', '記録あり', '# ログ\n')
        self.commit('app.py', '記録なしの作業')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('記録なしの作業', r.stderr)
        self.assertNotIn('記録あり', r.stderr)

    # --- 通す ---

    def test_記録が入っていれば通る(self):
        self.commit('checkpoints/2026-01-02-対応-記録.md', '作業と記録', '# ログ\n')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_理由付きの例外は通る(self):
        self.commit('app.py', '空白を整えた\n\n記録なし: 整形のみで作業ではない')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_英語のトレーラでも通る(self):
        self.commit('app.py', 'tidy\n\nNo-Record: formatting only')
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_押すものが無ければ黙る(self):
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_初回pushのような大量のcommitは対象外(self):
        for i in range(3):
            self.commit(f'app{i}.py', f'作業{i}')
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git push'},
                              'cwd': str(self.repo)})
        r = subprocess.run(['bash', '-c', f'CR_PUSH_MAX_COMMITS=2 bash {HOOK}'],
                           input=payload, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_マージcommitは見ない(self):
        git(self.repo, 'checkout', '-q', '-b', 'topic')
        self.commit('checkpoints/2026-01-03-枝-記録.md', '枝の作業', '# ログ\n')
        git(self.repo, 'checkout', '-q', 'main')
        self.commit('checkpoints/2026-01-04-幹-記録.md', '幹の作業', '# ログ\n')
        git(self.repo, 'merge', '--no-ff', '-m', 'マージ', 'topic')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pushでないコマンドは見ない(self):
        self.commit('app.py', 'コードを直した')
        for cmd in ('git status', 'git commit -m x', 'echo "git push"', 'git push --dry-run'):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 0, cmd)

    def test_通す指定があれば通る(self):
        self.commit('app.py', 'コードを直した')
        r = run_hook('CR_SKIP_RECORD_GUARD=1 git push', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_記録の方式を使っていないリポでは黙る(self):
        plain = Path(self.tmp.name) / 'plain'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(plain)],
                       check=True, capture_output=True)
        git(plain, 'config', 'user.email', 't@example.com')
        git(plain, 'config', 'user.name', 'test')
        git(plain, 'rm', '-q', '-r', 'checkpoints', 'PROGRESS.md')
        git(plain, 'commit', '-q', '-m', '記録の方式をやめる')
        (plain / 'app.py').write_text('x\n', encoding='utf-8')
        git(plain, 'add', '-A')
        git(plain, 'commit', '-q', '-m', '作業')
        self.assertEqual(run_hook('git push', plain).returncode, 0)

    def test_リモートが無ければ黙る(self):
        solo = Path(self.tmp.name) / 'solo'
        solo.mkdir()
        git(solo, 'init', '-q', '-b', 'main')
        git(solo, 'config', 'user.email', 't@example.com')
        git(solo, 'config', 'user.name', 'test')
        (solo / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        git(solo, 'add', '-A')
        git(solo, 'commit', '-q', '-m', '初期')
        (solo / 'app.py').write_text('x\n', encoding='utf-8')
        git(solo, 'add', '-A')
        git(solo, 'commit', '-q', '-m', '作業')
        self.assertEqual(run_hook('git push', solo).returncode, 0)

    def test_gitの外では黙る(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_hook('git push', d).returncode, 0)

    def test_呼ばれた印を残す(self):
        with tempfile.TemporaryDirectory() as d:
            payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'ls'},
                                  'cwd': str(self.repo)})
            subprocess.run(['bash', '-c', f'CLAUDE_CONFIG_DIR={d} bash {HOOK}'],
                           input=payload, text=True, capture_output=True)
            seen = Path(d) / '.record-guard-seen'
            self.assertTrue(seen.exists())
            self.assertRegex(seen.read_text().strip(), r'^\d+$')


if __name__ == '__main__':
    unittest.main()
