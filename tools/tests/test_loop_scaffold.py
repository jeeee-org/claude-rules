"""tools/loop-scaffold.pyと、それが入れるループのひな型（loopctl・フック・ゲート）のテスト。

  python3 -m unittest discover -s tools/tests

一時ディレクトリにひな型を入れ、コマンドとして実行して確かめる。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'loop-scaffold.py'


def scaffold(target, *args):
    return subprocess.run([sys.executable, str(TOOL), str(target), *args], capture_output=True, text=True)


class ScaffoldTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / '.git').mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_開発用のひな型が揃う(self):
        p = scaffold(self.root, '--profile', 'dev')
        self.assertEqual(p.returncode, 0, p.stderr)
        for rel in ['.claude/agents/loop-conductor.md', '.claude/agents/gate-judge.md',
                    '.claude/agents/dev-implement.md', '.claude/agents/review-test.md',
                    '.claude/loop/pipeline.json', '.claude/loop/bin/loopctl.py',
                    '.claude/loop/gates/lib.sh', '.claude/loop/gates/test.sh', '.claude/loop/.scaffold.json']:
            self.assertTrue((self.root / rel).exists(), rel)
        self.assertFalse((self.root / '.claude/agents/step-worker.md').exists())
        self.assertTrue(os.access(self.root / '.claude/loop/bin/loopctl.py', os.X_OK))

    def test_汎用のひな型は汎用の工程役を入れる(self):
        scaffold(self.root, '--profile', 'generic')
        self.assertTrue((self.root / '.claude/agents/step-worker.md').exists())
        self.assertFalse((self.root / '.claude/agents/dev-implement.md').exists())
        self.assertEqual(json.loads((self.root / '.claude/loop/pipeline.json').read_text())['profile'], 'generic')

    def test_既にあるファイルは上書きしない(self):
        f = self.root / '.claude/loop/GOAL.md'
        f.parent.mkdir(parents=True)
        f.write_text('手で書いた完了条件\n')
        p = scaffold(self.root, '--profile', 'dev')
        self.assertEqual(f.read_text(), '手で書いた完了条件\n')
        self.assertIn('既にあるので省略', p.stdout)
        scaffold(self.root, '--profile', 'dev', '--force')
        self.assertNotEqual(f.read_text(), '手で書いた完了条件\n')

    def test_確認だけなら何も書かない(self):
        p = scaffold(self.root, '--profile', 'dev', '--dry-run')
        self.assertEqual(p.returncode, 0)
        self.assertFalse((self.root / '.claude').exists())

    def test_settingsへフックを重複なく足し既存を残す(self):
        s = self.root / '.claude/settings.json'
        s.parent.mkdir(parents=True)
        s.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)']},
                                 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo mine'}]}]}}))
        scaffold(self.root, '--profile', 'dev')
        scaffold(self.root, '--profile', 'dev')
        data = json.loads(s.read_text())
        self.assertEqual(data['permissions'], {'allow': ['Bash(ls)']})
        cmds = [h['command'] for g in data['hooks']['Stop'] for h in g['hooks']]
        self.assertEqual(len(cmds), 2)
        self.assertIn('echo mine', cmds)
        self.assertEqual(len(data['hooks']['SubagentStop']), 1)
        self.assertTrue((self.root / '.claude/settings.json.bak').exists())

    def test_to_doはリポ単位で指定した時だけ有効にする(self):
        scaffold(self.root, '--profile', 'dev')
        data = json.loads((self.root / '.claude/settings.json').read_text())
        self.assertNotIn('env', data)
        scaffold(self.root, '--profile', 'dev', '--enable-todo')
        data = json.loads((self.root / '.claude/settings.json').read_text())
        self.assertEqual(data['env'], {'CLAUDE_CODE_ENABLE_TODO_TOOLS': '1'})
        self.assertEqual(len(data['hooks']['Stop']), 1)

    def test_フックなしでもto_doだけは足せる(self):
        scaffold(self.root, '--profile', 'dev', '--no-settings', '--enable-todo')
        data = json.loads((self.root / '.claude/settings.json').read_text())
        self.assertEqual(data, {'env': {'CLAUDE_CODE_ENABLE_TODO_TOOLS': '1'}})

    def test_settingsを触らない指定(self):
        scaffold(self.root, '--profile', 'dev', '--no-settings')
        self.assertFalse((self.root / '.claude/settings.json').exists())


class LoopRunTest(unittest.TestCase):
    """入れたひな型を一時リポで回す。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / '.git').mkdir()
        scaffold(self.root, '--profile', 'dev', '--no-settings')
        self.loop = self.root / '.claude/loop'
        self.env = dict(os.environ, LOOP_DIR=str(self.loop), LOOP_NOW='1000')

    def tearDown(self):
        self._tmp.cleanup()

    def ctl(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(self.loop / 'bin/loopctl.py'), *args],
                           capture_output=True, text=True, env=self.env, cwd=self.root)
        if ok:
            self.assertIn(p.returncode, (0,), p.stdout + p.stderr)
        return p

    def hook(self, name, payload):
        p = subprocess.run([sys.executable, str(self.loop / 'bin' / name)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env, cwd=self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if p.stdout.strip() else None

    def state(self):
        return json.loads((self.loop / 'state.json').read_text())

    def write_requirements(self):
        d = self.root / 'docs/loop'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'requirements.md').write_text('# 要件\n## REQ-01 ログイン\n受け入れ条件: テストが通る\n')

    def to_judge(self):
        self.ctl('begin')
        self.ctl('start', 'requirements')
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        self.write_requirements()
        self.ctl('gate', 'requirements')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'judge')

    # --- 順序と遷移 ---

    def test_前の工程が済むまで次は始められない(self):
        self.ctl('begin')
        p = self.ctl('start', 'design', ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertIn('requirements', p.stderr)

    def test_分担が全部提出されるまでレビューへ進まない(self):
        self.ctl('begin')
        self.ctl('start', 'requirements', '--shard', 'a')
        self.ctl('start', 'requirements', '--shard', 'b')
        self.ctl('submit', 'requirements', '--shard', 'a')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')
        self.ctl('submit', 'requirements', '--shard', 'b')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'review')

    def test_レビュー不合格は差し戻し上限で止まる(self):
        self.ctl('begin')
        for _ in range(4):
            self.ctl('start', 'requirements')
            self.ctl('submit', 'requirements')
            self.ctl('review', 'requirements', 'fail', '--note', '受け入れ条件が曖昧')
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'blocked')
        self.assertIn('上限', s['blocker'])

    # --- 決定論ゲート ---

    def test_ゲート不合格は作業中へ戻す(self):
        self.ctl('begin')
        self.ctl('start', 'requirements')
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        p = self.ctl('gate', 'requirements', ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn('requirements.md が無いか空', p.stdout)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')

    def test_コマンド未設定のゲートは通さない(self):
        env = dict(self.env, LOOP_STEP='implement', REPO_ROOT=str(self.root))
        p = subprocess.run(['bash', str(self.loop / 'gates/implement.sh')], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn('未設定', p.stdout)

    # --- 判断役 ---

    def test_確信度が閾値以上の合格は自動で通す(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.97, 'reason': 'x'}]}
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['judge']['audit_rate'] = 0
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg))
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        self.assertEqual(self.state()['steps']['requirements']['status'], 'done')
        row = json.loads((self.loop / 'judge/judgments.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['decision'], 'auto_pass')

    def test_確信度が低ければ人へ回し人の答えが正解として残る(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.6}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'blocked')
        self.assertTrue(s['needs_human'])
        self.ctl('decide', 'requirements', 'fail', '--note', '意図の取り違え')
        row = json.loads((self.loop / 'judge/judgments.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['human_answer'], 'not:yes')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')

    def test_確信度の高い不合格は自動で差し戻す(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'no', 'confidence': 0.95, 'reason': '範囲が違う'}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'in_progress')
        self.assertIn('範囲が違う', s['notes'][-2]['text'])

    def test_選択肢の外の答えは人へ回す(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'maybe', 'confidence': 0.99}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        self.assertTrue(self.state()['steps']['requirements']['needs_human'])

    def test_較正は正答率が目標に届く最小の確信度を閾値にする(self):
        rows = []
        # 確信度0.9以上は全問正解、0.7台は半分誤り
        for i in range(25):
            rows.append({'id': f'a{i}', 'step': 's', 'question': 'q', 'answer': 'yes', 'confidence': 0.9 + i * 0.001,
                         'human_answer': 'yes'})
        for i in range(10):
            rows.append({'id': f'b{i}', 'step': 's', 'question': 'q', 'answer': 'yes', 'confidence': 0.7,
                         'human_answer': 'yes' if i % 2 else 'not:yes'})
        (self.loop / 'judge/judgments.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        p = self.ctl('calibrate', '--apply')
        th = json.loads((self.loop / 'judge/calibration.json').read_text())['thresholds']['q']
        self.assertAlmostEqual(th, 0.9, places=3)
        self.assertIn('0.70', (self.loop / 'judge/lessons.md').read_text())
        self.assertIn('閾値 0.90', p.stdout)

    def test_標本が足りなければ自動にしない(self):
        rows = [{'id': 'a', 'step': 's', 'question': 'q', 'answer': 'yes', 'confidence': 0.99, 'human_answer': 'yes'}]
        (self.loop / 'judge/judgments.jsonl').write_text(json.dumps(rows[0]) + '\n')
        self.ctl('calibrate', '--apply')
        th = json.loads((self.loop / 'judge/calibration.json').read_text())['thresholds']['q']
        self.assertGreater(th, 1.0)

    def test_後から訂正した答えが較正に効く(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.97}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        jid = json.loads((self.loop / 'judge/judgments.jsonl').read_text().splitlines()[0])['id']
        self.ctl('override', jid, 'no', '--note', '実は取り違え')
        row = json.loads((self.loop / 'judge/judgments.jsonl').read_text().splitlines()[0])
        self.assertEqual(row['human_answer'], 'no')

    # --- Stopフック（公式の早止まり対策） ---

    def stop(self, **kw):
        payload = {'hook_event_name': 'Stop', 'agent_type': 'loop-conductor', 'background_tasks': []}
        payload.update(kw)
        return self.hook('stop-guard.py', payload)

    def test_未完了があれば残りを名指しして続けさせる(self):
        self.ctl('begin')
        out = self.stop()
        self.assertEqual(out['decision'], 'block')
        self.assertIn('requirements', out['reason'])

    def test_統括役でないセッションには催促しない(self):
        self.ctl('begin')
        self.assertIsNone(self.stop(agent_type=None))

    def test_バックグラウンドの作業中は催促しない(self):
        self.ctl('begin')
        self.assertIsNone(self.stop(background_tasks=[{'id': 't', 'type': 'subagent'}]))

    def test_状態が進まないまま上限を超えたら実行を止める(self):
        self.ctl('begin')
        for _ in range(3):
            self.assertEqual(self.stop()['decision'], 'block')
        out = self.stop()
        self.assertIn('systemMessage', out)
        self.assertFalse(self.state()['active'])

    def test_状態が進めば数え直す(self):
        self.ctl('begin')
        self.stop(); self.stop()
        self.ctl('start', 'requirements')
        self.stop(); self.stop()
        self.assertEqual(self.stop()['decision'], 'block')

    def test_残りが全部人待ちなら止まってよい(self):
        self.ctl('begin', '--only', 'requirements')
        self.ctl('block', 'requirements', '顧客の回答待ち')
        self.assertIsNone(self.stop())

    def test_一時停止中は催促しない(self):
        self.ctl('begin')
        self.ctl('pause')
        self.assertIsNone(self.stop())

    # --- SubagentStopフック ---

    def sub(self, agent, msg, active=False):
        return self.hook('subagent-report-guard.py', {'hook_event_name': 'SubagentStop', 'agent_type': agent,
                                                      'last_assistant_message': msg, 'stop_hook_active': active})

    def test_報告の形が無い工程役は一度だけ差し戻す(self):
        self.assertEqual(self.sub('dev-implement', '実装しました。次はテストを書きます。')['decision'], 'block')
        self.assertIsNone(self.sub('dev-implement', '実装しました。', active=True))
        self.assertIsNone(self.sub('dev-implement', 'やったこと\nSTATUS: done\n成果物: src/a.ts'))

    def test_ループ外のサブエージェントには口を出さない(self):
        self.assertIsNone(self.sub('Explore', '調べました'))

    def test_判断役はJSONで返せば通す(self):
        self.assertIsNone(self.sub('gate-judge', '{"answers": []}'))
        self.assertEqual(self.sub('gate-judge', 'yesだと思います')['decision'], 'block')


if __name__ == '__main__':
    unittest.main()
