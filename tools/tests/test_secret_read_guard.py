"""hooks/secret-read-guard.pyのテスト — 資格情報のファイルを丸ごと出力する読み方を止める。

exit 0 = 通す／exit 2 = 止めて差し戻す。
"""
import json
import os
import subprocess
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / 'hooks' / 'secret-read-guard.py'
HOME = os.path.expanduser('~')


def run(tool, **ti):
    payload = json.dumps({'tool_name': tool, 'tool_input': ti})
    return subprocess.run(['python3', str(HOOK)], input=payload, text=True, capture_output=True).returncode


class SecretReadGuardTest(unittest.TestCase):
    def test_中身を出す読み方は止める(self):
        for cmd in ['cat ~/.claude.json', f'cat {HOME}/.claude.json | jq keys', 'jq . $HOME/.claude.json',
                    "jq '.mcpServers' ~/.claude.json", "jq 'keys, .primaryApiKey' ~/.claude.json",
                    'head -5 ~/.aws/credentials', 'grep API_KEY .env', 'cat .env.local', 'cat ~/.ssh/id_ed25519',
                    'cat ~/.codex/auth.json', f'python3 - <<EOF\nprint(open("{HOME}/.claude.json").read())\nEOF']:
            with self.subTest(cmd=cmd):
                self.assertEqual(run('Bash', command=cmd), 2)

    def test_キーの有無や件数だけの読み方は通す(self):
        for cmd in ["jq 'keys' ~/.claude.json", 'jq keys ~/.claude.json', "jq -r '.mcpServers | keys' $HOME/.claude.json",
                    """jq 'has("primaryApiKey")' ~/.claude.json""", 'grep -c API_KEY .env', "grep -q '^TOKEN=' .env && echo ある",
                    'ls -la ~/.aws/credentials', 'test -f ~/.claude.json', 'cat .env.example', 'cat ~/.ssh/id_ed25519.pub',
                    'cat ~/.claude/settings.json', 'CR_SKIP_SECRET_GUARD=1 cat ~/.claude.json']:
            with self.subTest(cmd=cmd):
                self.assertEqual(run('Bash', command=cmd), 0)

    def test_文章に名前が出るだけのコマンドは止めない(self):
        self.assertEqual(run('Bash', command='git commit -m "cat .env と cat ~/.claude.json を止める"'), 0)
        self.assertEqual(run('Bash', command='python3 - <<EOF\nprint("cat .env")\nEOF'), 0)
        self.assertEqual(run('Bash', command='python3 - <<EOF\ns = "資格情報（`~/.claude.json`等）を丸ごと出す"\nEOF'), 0)

    def test_ReadとGrepは資格情報のファイルの中身を返す時だけ止める(self):
        self.assertEqual(run('Read', file_path=f'{HOME}/.claude.json'), 2)
        self.assertEqual(run('Read', file_path='/x/proj/.env'), 2)
        self.assertEqual(run('Read', file_path='/x/proj/.envrc'), 0)
        self.assertEqual(run('Read', file_path='/x/proj/.env.sample'), 0)
        self.assertEqual(run('Grep', path=f'{HOME}/.claude.json', output_mode='content'), 2)
        self.assertEqual(run('Grep', path=f'{HOME}/.claude.json'), 0)

    def test_読めない入力は通す(self):
        r = subprocess.run(['python3', str(HOOK)], input='not json', text=True, capture_output=True)
        self.assertEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
