"""hooks/push-attribution-guard.shのテスト — AI帰属行の関門（pushの直前に見る）。

commitは既にあるので、メッセージの渡し方（-m / -F / エディタ）によらず読める。
exit 0 = 通す（fail-openを含む）／exit 2 = 止めて差し戻す。
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'hooks' / 'push-attribution-guard.sh'

ATTRIBUTION = 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>'


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          capture_output=True, text=True)


def run_hook(command, cwd, tool_name='Bash'):
    payload = json.dumps({'tool_name': tool_name, 'tool_input': {'command': command},
                          'cwd': str(cwd)})
    return subprocess.run(['bash', str(HOOK)], input=payload, text=True, capture_output=True)


class AttributionGuardTest(unittest.TestCase):
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
        (self.repo / 'README.md').write_text('# repo\n', encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', '初期')
        git(self.repo, 'push', '-q', '-u', 'origin', 'main')

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, message, text='x\n'):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        git(self.repo, 'add', '-A')
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-q', '-F', '-'],
                       input=message, text=True, check=True, capture_output=True)

    # --- 止める ---

    def test_Co_Authored_Byが入っていると止まる(self):
        self.commit('app.py', f'着手宣言\n\n{ATTRIBUTION}')
        r = run_hook('git push', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('着手宣言', r.stderr)          # どのcommitかを名指しする
        self.assertIn('--amend', r.stderr)           # 直し方を案内する
        self.assertIn('forceは要りません', r.stderr)  # 押す前なら軽いことを言う

    def test_宣伝行でも止まる(self):
        self.commit('app.py', '作業\n\n🤖 Generated with Claude Code')
        self.assertEqual(run_hook('git push', self.repo).returncode, 2)

    def test_メールアドレスだけでも止まる(self):
        self.commit('app.py', '作業\n\nSigned-off-by: someone <noreply@anthropic.com>')
        self.assertEqual(run_hook('git push', self.repo).returncode, 2)

    def test_大文字小文字は問わない(self):
        self.commit('app.py', '作業\n\nco-authored-by: CLAUDE <x@example.com>')
        self.assertEqual(run_hook('git push', self.repo).returncode, 2)

    def test_メッセージのトレーラでは抜けられない(self):
        """記録の関門と違い、問題にしているのがメッセージそのものなので例外を置かない"""
        self.commit('app.py', f'作業\n\n記録なし: 整形のみ\n{ATTRIBUTION}')
        self.assertEqual(run_hook('git push', self.repo).returncode, 2)

    def test_書き方によらず判定できる(self):
        self.commit('app.py', f'着手宣言\n\n{ATTRIBUTION}')
        for cmd in ('git push', f'cd {self.repo} && git push',
                    f'git -C {self.repo} push origin main',
                    "cat >> a.md <<'EOF'\n追記\nEOF\ngit push"):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 2, cmd)

    def test_記録の方式を使っていないリポでも見る(self):
        """規約は全リポに効く。記録の関門と違い、リポの作りで対象を絞らない"""
        self.assertFalse((self.repo / 'PROGRESS.md').exists())
        self.commit('app.py', f'作業\n\n{ATTRIBUTION}')
        self.assertEqual(run_hook('git push', self.repo).returncode, 2)

    # --- 通す ---

    def test_署名の形でなければ通る(self):
        """本文にClaudeと書くこと自体は止めない（Botについて書いたcommitが作れなくなる）"""
        self.commit('app.py', 'Claudeの応答を保存する処理を足した')
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_人間の共著者は通る(self):
        self.commit('app.py', '作業\n\nCo-Authored-By: someone <someone@example.com>')
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_通す指定があれば通る(self):
        self.commit('app.py', f'作業\n\n{ATTRIBUTION}')
        r = run_hook('CR_SKIP_ATTRIBUTION_GUARD=1 git push', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_amendで落とせば通る(self):
        self.commit('app.py', f'着手宣言\n\n{ATTRIBUTION}')
        git(self.repo, 'commit', '-q', '--amend', '-m', '着手宣言')
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_押すものが無ければ黙る(self):
        self.assertEqual(run_hook('git push', self.repo).returncode, 0)

    def test_pushでないコマンドは見ない(self):
        self.commit('app.py', f'作業\n\n{ATTRIBUTION}')
        for cmd in ('git status', 'git commit -m x', 'echo "git push"',
                    'git push --dry-run', 'git push --delete origin topic'):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_hook(cmd, self.repo).returncode, 0, cmd)

    def test_押し出す数が多ければ対象外(self):
        for i in range(3):
            self.commit(f'app{i}.py', f'作業{i}\n\n{ATTRIBUTION}')
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git push'},
                              'cwd': str(self.repo)})
        r = subprocess.run(['bash', '-c', f'CR_PUSH_MAX_COMMITS=2 bash {HOOK}'],
                           input=payload, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_リモートが無ければ黙る(self):
        solo = Path(self.tmp.name) / 'solo'
        solo.mkdir()
        git(solo, 'init', '-q', '-b', 'main')
        git(solo, 'config', 'user.email', 't@example.com')
        git(solo, 'config', 'user.name', 'test')
        (solo / 'app.py').write_text('x\n', encoding='utf-8')
        git(solo, 'add', '-A')
        subprocess.run(['git', '-C', str(solo), 'commit', '-q', '-F', '-'],
                       input=f'作業\n\n{ATTRIBUTION}', text=True, check=True, capture_output=True)
        self.assertEqual(run_hook('git push', solo).returncode, 0)

    def test_gitの外では黙る(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run_hook('git push', d).returncode, 0)

    def test_Bash以外のツールは見ない(self):
        self.commit('app.py', f'作業\n\n{ATTRIBUTION}')
        self.assertEqual(run_hook('git push', self.repo, tool_name='Edit').returncode, 0)


if __name__ == '__main__':
    unittest.main()
