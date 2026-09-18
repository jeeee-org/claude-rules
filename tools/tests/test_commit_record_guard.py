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

    def other_repo(self):
        """記録の方式は使うが、まだ記録を書いていない別のリポ"""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(d)]))
        git(d, 'init', '-b', 'main')
        git(d, 'config', 'user.email', 't@example.com')
        git(d, 'config', 'user.name', 'test')
        (d / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        (d / 'app.py').write_text('x = 1\n', encoding='utf-8')
        git(d, 'add', '-A')
        git(d, 'commit', '-m', '初期')
        return d

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
        other = self.other_repo()
        (other / 'app.py').write_text('x = 2\n', encoding='utf-8')
        # 実行元は記録を書き終えたリポでも、commitするのは別のリポ
        self.touch('PROGRESS.md', '# 進捗\n更新\n')
        r = run_hook(f'cd {other} && git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 2)

    def test_git_Cで指したリポで判定する(self):
        """cwdが記録を書き終えたリポでも、-Cが指すリポに記録が無ければ止める"""
        other = self.other_repo()
        (other / 'app.py').write_text('x = 2\n', encoding='utf-8')
        self.touch('PROGRESS.md', '# 進捗\n更新\n')   # 実行元には記録がある
        r = run_hook(f'git -C {other} add -A && git -C {other} commit -m x', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn(str(other), r.stderr)   # どのリポを見たかを言う

    def test_git_Cはcdより優先する(self):
        """実際のgitと同じ順。cd先に記録があっても、-C先に無ければ止める"""
        other = self.other_repo()
        (other / 'app.py').write_text('x = 2\n', encoding='utf-8')
        self.touch('PROGRESS.md', '# 進捗\n更新\n')
        r = run_hook(f'cd {self.repo} && git -C {other} commit -am x', self.repo)
        self.assertEqual(r.returncode, 2)

    def test_疎通確認の印は状態にかかわらず必ず止める(self):
        """②で使う印。記録があっても、gitの外でも止まる＝呼ばれていれば必ず分かる"""
        self.touch('PROGRESS.md', '# 進捗\n更新\n')   # 本来なら通る状態
        r = run_hook(f'CR_RECORD_GUARD_PROBE=1 git -C {self.repo} commit --dry-run', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('発火しています', r.stderr)
        with tempfile.TemporaryDirectory() as d:   # gitの外でも止まる
            r = run_hook('CR_RECORD_GUARD_PROBE=1 git commit --dry-run', d)
            self.assertEqual(r.returncode, 2)

    def test_本文に印の名前を書いても誤作動しない(self):
        """ヒアドキュメントの中身は見ない。フックを説明する文書を書いた時に実際に誤作動した"""
        self.touch('app.py', 'x = 2\n')
        # 通す指定の名前を本文に書いただけでは、関門は外れない
        r = run_hook("git commit -F - <<'EOF'\n通すにはCR_SKIP_RECORD_GUARD=1を付ける\nEOF", self.repo)
        self.assertEqual(r.returncode, 2)
        # 疎通確認の印を本文に書いただけでは止まらない（記録があるので通る）
        self.touch('PROGRESS.md', '# 進捗\n更新\n')
        r = run_hook("git commit -F - <<'EOF'\n確認はCR_RECORD_GUARD_PROBE=1で行う\nEOF", self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ヒアドキュメントの後ろのcommitも検出する(self):
        """`<<`から後ろを全部切っていたため、この形が素通りしていた（2台で実測）"""
        self.touch('app.py', 'x = 2\n')
        cmd = ("cat >> app.py <<'EOF'\n# 追記\nEOF\n"
               "git add -A && git commit -m x")
        r = run_hook(cmd, self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('分けて', r.stderr)

    def test_書き込みとcommitが同じ呼び出しなら判定せず分割を求める(self):
        """PreToolUseの時点では書き込みが起きていないので、記録が入るか分からない"""
        self.touch('app.py', 'x = 2\n')
        for cmd in ("printf 'x\\n' > memo.txt && git add -A && git commit -m x",
                    "cp a b; git commit -am x",
                    "python3 write.py && git add -A && git commit -m x"):
            with self.subTest(cmd=cmd):
                r = run_hook(cmd, self.repo)
                self.assertEqual(r.returncode, 2, cmd)
                self.assertIn('分けてください', r.stderr)

    def test_変更なしから一気に作る形も止まる(self):
        """cleanなリポでは「変更なし」で通っていた。書き込みの気配で止める"""
        clean = self.other_repo()   # 作業ツリーはclean
        cmd = f"printf 'x\\n' > {clean}/app.py && git -C {clean} add -A && git -C {clean} commit -m x"
        r = run_hook(cmd, self.repo)
        self.assertEqual(r.returncode, 2)

    def test_差し戻しの文面はコマンド全体が実行されないことを言う(self):
        """「commitだけ止まった」と読むと、次のcommitがno changesで空振りする"""
        self.touch('app.py', 'x = 2\n')
        r = run_hook('git add -A && git commit -m x', self.repo)
        self.assertEqual(r.returncode, 2)
        self.assertIn('1行も実行されていません', r.stderr)

    # --- 通す ---

    def test_git_Cの先に記録があれば通る(self):
        other = self.other_repo()
        (other / 'checkpoints').mkdir()
        (other / 'checkpoints' / '2026-01-02-対応-切り分け.md').write_text('# ログ\n', encoding='utf-8')
        self.touch('app.py', 'x = 2\n')   # 実行元には記録が無い
        r = run_hook(f'git -C {other} add -A && git -C {other} commit -m x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_解けない_Cの指定は判定しない(self):
        """変数展開などで行き先が分からない時は、別のリポを見て誤るより通す"""
        self.touch('app.py', 'x = 2\n')
        r = run_hook('git -C "$d" commit -am x', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_git_addだけなら書き込み扱いにしない(self):
        """addはディスク上の変更を載せるだけ。判定できるので、記録があれば通す"""
        self.touch('app.py', 'x = 2\n')
        self.touch('checkpoints/2026-01-03-対応-記録.md', '# ログ\n')
        r = run_hook('git add -A && git commit -q -F - <<\'EOF\'\n件名\nEOF', self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

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


class AuditTest(unittest.TestCase):
    """hooks/commit-record-audit.sh — できてしまったcommitを後から見る網"""

    AUDIT = Path(__file__).resolve().parents[2] / 'hooks' / 'commit-record-audit.sh'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-b', 'main')
        git(self.repo, 'config', 'user.email', 't@example.com')
        git(self.repo, 'config', 'user.name', 'test')
        (self.repo / 'PROGRESS.md').write_text('# 進捗\n', encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', '初期')

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text='x\n'):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-m', 'あとで')

    def run_audit(self, command):
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command},
                              'cwd': str(self.repo)})
        return subprocess.run(['bash', str(self.AUDIT)], input=payload, text=True,
                              capture_output=True)

    def test_記録の無いcommitができていたら知らせる(self):
        self.commit('app.py')
        r = self.run_audit('cat > app.py <<EOF\nx\nEOF\ngit add -A && git commit -m x')
        self.assertEqual(r.returncode, 2)
        self.assertIn('後追い', r.stderr)
        self.assertIn(str(self.repo), r.stderr)

    def test_記録が入っていれば黙る(self):
        self.commit('checkpoints/2026-01-02-対応-記録.md', '# ログ\n')
        r = self.run_audit('git add -A && git commit -m x')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_commitを含まない呼び出しは見ない(self):
        self.commit('app.py')
        self.assertEqual(self.run_audit('ls -la').returncode, 0)

    def test_古いcommitは蒸し返さない(self):
        self.commit('app.py')
        env_cmd = ['bash', '-c',
                   f'CR_AUDIT_FRESH_SECONDS=0 bash {self.AUDIT}']
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m x'},
                              'cwd': str(self.repo)})
        r = subprocess.run(env_cmd, input=payload, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_記録の方式を使っていないリポでは黙る(self):
        plain = Path(self.tmp.name) / 'plain'
        plain.mkdir()
        git(plain, 'init', '-b', 'main')
        git(plain, 'config', 'user.email', 't@example.com')
        git(plain, 'config', 'user.name', 'test')
        (plain / 'app.py').write_text('x\n', encoding='utf-8')
        git(plain, 'add', '-A')
        git(plain, 'commit', '-m', '初期')
        payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m x'},
                              'cwd': str(plain)})
        r = subprocess.run(['bash', str(self.AUDIT)], input=payload, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class CheckGuardTest(unittest.TestCase):
    """tools/check-record-guard.sh — 関門が効いているかを確かめるコマンド"""

    CHECK = Path(__file__).resolve().parents[1] / 'check-record-guard.sh'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'work'
        self.repo.mkdir()
        git(self.repo, 'init', '-b', 'main')

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, hook=HOOK, repo=None):
        return subprocess.run(['bash', str(self.CHECK), '--hook', str(hook),
                               '--repo', str(repo if repo else self.repo)],
                              capture_output=True, text=True)

    def test_判定が正しければ作業するリポで試すコマンドを出す(self):
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('スクリプトの判定: 正しい', r.stdout)
        # ②は使い捨てではなく、これから作業するリポを指す
        self.assertIn(f'CR_RECORD_GUARD_PROBE=1 git -C {self.repo.resolve()} commit --dry-run', r.stdout)
        self.assertIn('--dry-run なので', r.stdout)   # 呼ばれなくても何もコミットされない
        # 作業するリポの中には何も作らない
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['.git'])

    def test_止めないスクリプトなら失敗で返す(self):
        stub = Path(self.tmp.name) / 'stub.sh'
        stub.write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
        r = self.run_check(hook=stub)
        self.assertEqual(r.returncode, 1)
        self.assertIn('止めませんでした', r.stderr)

    def test_gitリポでなければ中止する(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_check(repo=d)
            self.assertEqual(r.returncode, 2)
            self.assertIn('gitリポジトリではありません', r.stderr)


if __name__ == '__main__':
    unittest.main()
