"""hooks/git-commit-msg.shのテスト — gitのcommit-msgフック（AI帰属行を取り除く）。

Claude Codeの関門をすり抜ける形（commitとpushを同じ呼び出し・スクリプトの中のpush）でも、
git自身が呼ぶので漏れない（IMPROVEMENTS 2026-09-28）。実際にcommitして確かめる。
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'hooks' / 'git-commit-msg.sh'
ATTRIBUTION = 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>'


class GitCommitMsgTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'work'
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.repo)], check=True)
        self.git('config', 'user.email', 't@example.com')
        self.git('config', 'user.name', 'test')
        hooks = self.repo / '.git' / 'hooks'
        hooks.mkdir(exist_ok=True)
        shutil.copy2(HOOK, hooks / 'commit-msg')
        (hooks / 'commit-msg').chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, env=None, input=None):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              text=True, env=env, input=input)

    def commit(self, message, env=None):
        (self.repo / 'a.txt').write_text(message, encoding='utf-8')
        self.git('add', '-A')
        r = self.git('commit', '-q', '-F', '-', input=message, env=env)
        return self.git('log', '-1', '--format=%B').stdout.rstrip('\n'), r.stderr

    def test_帰属行を取り除き何を消したかを出す(self):
        body, err = self.commit(f'作業\n\n本文\n\n{ATTRIBUTION}\n')
        self.assertEqual(body, '作業\n\n本文')
        self.assertIn('取り除きました', err)

    def test_宣伝行も取り除く(self):
        body, _ = self.commit('作業\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n')
        self.assertEqual(body, '作業')

    def test_人の共著者と本文のClaudeは残す(self):
        msg = '帰属行の関門でClaudeの指示を止める\n\nCo-Authored-By: Taro <taro@example.com>'
        body, err = self.commit(msg)
        self.assertEqual(body, msg)
        self.assertEqual(err, '')

    def test_通す指定なら残す(self):
        env = dict(os.environ, CR_SKIP_ATTRIBUTION_GUARD='1')
        body, _ = self.commit(f'作業\n\n{ATTRIBUTION}', env=env)
        self.assertIn(ATTRIBUTION, body)

    def test_前からあったフックを続けて呼ぶ(self):
        local = self.repo / '.git' / 'hooks' / 'commit-msg.local'
        local.write_text('#!/bin/sh\necho "local-ran" >> "$1"\n', encoding='utf-8')
        local.chmod(0o755)
        body, _ = self.commit(f'作業\n\n{ATTRIBUTION}')
        self.assertEqual(body, '作業\nlocal-ran')

    def test_前からあったフックが拒めばcommitも止まる(self):
        local = self.repo / '.git' / 'hooks' / 'commit-msg.local'
        local.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        local.chmod(0o755)
        with self.assertRaises(subprocess.CalledProcessError):
            self.commit('作業')


if __name__ == '__main__':
    unittest.main()
