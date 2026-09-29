"""tools/loop-scaffold.pyと、それが入れるループのひな型（loopctl・フック・ゲート）のテスト。

  python3 -m unittest discover -s tools/tests

一時ディレクトリにひな型を入れ、コマンドとして実行して確かめる。
"""
import json
import os
import shutil
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

    def test_汎用のひな型はコミットの工程とゲートを持つ(self):
        scaffold(self.root, '--profile', 'generic')
        cfg = json.loads((self.root / '.claude/loop/pipeline.json').read_text())
        commit = [x for x in cfg['steps'] if x['id'] == 'commit'][0]
        self.assertEqual(commit['gate'], 'gates/commit.sh')
        self.assertIn('別のBash呼び出し', commit['instructions'])
        self.assertTrue((self.root / '.claude/loop/gates/commit.sh').exists())
        self.assertIn('ループの仕組みの課題', (self.root / '.claude/loop/candidates.md').read_text())

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
        self.assertEqual([g['matcher'] for g in data['hooks']['PreToolUse']], ['Bash'])
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

    def test_settingsがgitの無視対象なら知らせる(self):
        shutil.rmtree(self.root / '.git')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / '.gitignore').write_text('.claude/settings.json\n')
        p = scaffold(self.root, '--profile', 'dev')
        self.assertIn('gitの無視対象です: .claude/settings.json', p.stdout)
        self.assertNotIn('pipeline.json', p.stdout.split('無視対象です')[1].splitlines()[0])
        (self.root / '.gitignore').write_text('')
        p = scaffold(self.root, '--profile', 'dev')
        self.assertNotIn('無視対象', p.stdout)

    def test_名前を付けると2つ目のループを並べて置ける(self):
        scaffold(self.root, '--profile', 'dev')
        p = scaffold(self.root, '--profile', 'generic', '--name', 'audit')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('claude --agent audit-loop-conductor', p.stdout)
        ag = self.root / '.claude/agents'
        self.assertTrue((ag / 'loop-conductor.md').exists())
        self.assertTrue((ag / 'audit-step-worker.md').exists())
        self.assertFalse((ag / 'step-worker.md').exists())
        cond = (ag / 'audit-loop-conductor.md').read_text()
        self.assertIn('name: audit-loop-conductor', cond)
        self.assertIn('.claude/loop-audit/bin/loopctl.py', cond)
        self.assertIn('`audit-gate-judge`を起こし', cond)
        self.assertNotIn('.claude/loop/', cond)
        cfg = json.loads((self.root / '.claude/loop-audit/pipeline.json').read_text())
        self.assertEqual(cfg['conductor'], 'audit-loop-conductor')
        self.assertEqual(cfg['judge']['agent'], 'audit-gate-judge')
        self.assertEqual({s['worker'] for s in cfg['steps']}, {'audit-step-worker'})
        self.assertIn('loop-out/', json.dumps(cfg))  # 成果物のパスは付け替えない
        hooks = json.loads((self.root / '.claude/settings.json').read_text())['hooks']
        cmds = [h['command'] for g in hooks['Stop'] for h in g['hooks']]
        self.assertEqual(len(cmds), 2)
        self.assertTrue(any('.claude/loop-audit/bin/stop-guard.py' in c for c in cmds))
        self.assertEqual(json.loads((self.root / '.claude/loop-audit/.scaffold.json').read_text())['name'], 'audit')
        # 道具は自分の置き場を見る
        env = dict(os.environ, LOOP_NOW='1000')
        env.pop('LOOP_DIR', None)
        r = subprocess.run([sys.executable, str(self.root / '.claude/loop-audit/bin/loopctl.py'), 'begin'],
                           capture_output=True, text=True, env=env, cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / '.claude/loop-audit/state.json').exists())
        self.assertFalse((self.root / '.claude/loop/state.json').exists())

    def test_名前は決まった文字だけ(self):
        self.assertEqual(scaffold(self.root, '--profile', 'dev', '--name', 'A b').returncode, 2)

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
        # 判断役の自動の経路を見るテストが多いので、既定は「任せる」段階（数値の閾値）で回す。
        # 較正前は人へ回す既定（null）は、それを見るテストで戻す
        self.set_default_threshold(0.9)

    def set_default_threshold(self, v):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['judge']['default_threshold'] = v
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))

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

    def test_前の実行の成果物が残ったままならゲートで落とし書き直せば通す(self):
        self.write_requirements()
        f = self.root / 'docs/loop/requirements.md'
        os.utime(f, (500, 500))  # 実行の開始（LOOP_NOW=1000）より前に書かれた
        p = self.ctl('begin')
        self.assertIn('前の実行の成果物が残っています', p.stderr)
        self.ctl('start', 'requirements')
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        p = self.ctl('gate', 'requirements', ok=False)
        self.assertIn('開始より前のまま', p.stdout)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')
        self.write_requirements()  # 書き直す（更新時刻が今になる）
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        p = self.ctl('gate', 'requirements')
        self.assertIn('この実行で書かれた', p.stdout)

    def test_成果物が無ければ始める時に知らせない(self):
        self.assertNotIn('前の実行の成果物', self.ctl('begin').stderr)

    def test_工程役にはコミットの状態を成果物に書かせない(self):
        for f in ('generic/.claude/agents/step-worker.md', 'dev/.claude/agents/dev-requirements.md',
                  'dev/.claude/agents/dev-design.md', 'dev/.claude/agents/dev-implement.md',
                  'dev/.claude/agents/dev-test.md'):
            self.assertIn('成果物にコミットの状態を書かない', (TOOL.parents[1] / 'templates/loop' / f).read_text())

    def test_コマンド未設定のゲートは通さない(self):
        env = dict(self.env, LOOP_STEP='implement', REPO_ROOT=str(self.root))
        p = subprocess.run(['bash', str(self.loop / 'gates/implement.sh')], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn('未設定', p.stdout)

    # --- 判断役 ---

    def test_較正前は確信度が高くても人へ回す(self):
        for prof in ('dev', 'generic'):  # ひな型の既定は null
            cfg = json.loads((TOOL.parents[1] / 'templates/loop' / prof / '.claude/loop/pipeline.json').read_text())
            self.assertIsNone(cfg['judge']['default_threshold'])
        self.set_default_threshold(None)
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.99, 'reason': 'x'}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'blocked')
        self.assertTrue(s['needs_human'])
        self.assertIn('較正前', s['blocker'])

    def test_較正で閾値が出た問いは任せる(self):
        self.set_default_threshold(None)
        self.to_judge()
        (self.loop / 'judge').mkdir(exist_ok=True)
        (self.loop / 'judge/calibration.json').write_text(json.dumps({'thresholds': {'req-intent': 0.9}}))
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['judge']['audit_rate'] = 0
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg))
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.95, 'reason': 'x'}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        self.assertEqual(self.state()['steps']['requirements']['status'], 'done')

    def test_確信度が閾値以上の合格は自動で通す(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.97, 'reason': 'x'}]}
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['judge']['audit_rate'] = 0
        cfg['judge']['default_threshold'] = 0.9  # 最初から任せるリポは数値を書く（以前の既定の動き）
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

    def test_選択肢の外の答えは判断役へ1回だけ選び直させ2回目は推奨なしで人へ回す(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'pass', 'confidence': 0.99}]}
        p = self.ctl('judge', 'requirements', '--answers', json.dumps(ans), ok=False)
        self.assertIn('選択肢の外', p.stderr)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'judge')
        self.assertFalse((self.loop / 'judge/judgments.jsonl').exists())
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        self.assertTrue(self.state()['steps']['requirements']['needs_human'])
        pend = json.loads(self.ctl('pending', '--json').stdout)
        self.assertIsNone(pend[0]['recommend'])
        # 推奨が無いので、推奨どおりの一括の答えでは中身を見ない差し戻しにならない
        self.ctl('answer', '--recommended', ok=False)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'blocked')

    def test_差し戻し後の判断ではもう一度選び直させる(self):
        self.to_judge()
        bad = {'answers': [{'id': 'req-intent', 'answer': 'pass', 'confidence': 0.99}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(bad), ok=False)
        self.ctl('judge', 'requirements', '--answers', json.dumps({'answers': [{'id': 'req-intent', 'answer': 'no', 'confidence': 0.95}]}))
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        self.ctl('gate', 'requirements')
        p = self.ctl('judge', 'requirements', '--answers', json.dumps(bad), ok=False)
        self.assertIn('選択肢の外', p.stderr)

    def test_人の答えが続けて判断役と同じ問いは見直しを促す(self):
        rows = [{'id': f'a{i}', 't': i, 'step': 's', 'question': 'q', 'answer': 'yes', 'confidence': 0.6, 'human_answer': 'yes'}
                for i in range(10)]
        rows.append({'id': 'b', 't': -1, 'step': 's', 'question': 'r', 'answer': 'yes', 'confidence': 0.6, 'human_answer': 'no'})
        (self.loop / 'judge/judgments.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        out = self.ctl('calibrate').stdout
        self.assertIn('直近10件続けて', out)
        self.assertEqual(out.count('直近'), 1)

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

    def test_全工程が完了したら閉じるよう促し閉じなければ閉じる(self):
        self.ctl('begin')
        st = self.state()
        for s in st['steps'].values():
            s['status'] = 'done'
        (self.loop / 'state.json').write_text(json.dumps(st, ensure_ascii=False))
        for _ in range(3):
            out = self.stop()
            self.assertEqual(out['decision'], 'block')
            self.assertIn('finish', out['reason'])
        out = self.stop()
        self.assertIn('実行を閉じました', out['systemMessage'])
        st = self.state()
        self.assertEqual((st['active'], st['finished']), (False, True))
        self.assertIsNone(self.stop())

    def test_人待ちで止まる時は閉じるよう促さない(self):
        self.ctl('begin')
        st = self.state()
        for s in st['steps'].values():
            s['status'] = 'done'
        next(iter(st['steps'].values()))['status'] = 'blocked'
        (self.loop / 'state.json').write_text(json.dumps(st, ensure_ascii=False))
        self.assertIsNone(self.stop())

    def test_集約の工程が待たない枝をbeginが知らせる(self):
        def fn(cfg):
            ids = [s['id'] for s in cfg['steps']]
            cfg['steps'][-1]['after'] = ids[:2]      # 最後の工程が2つを集約する
            cfg['steps'][2]['after'] = [ids[0]]     # 3つ目は枝。集約の前提に入っていない
        self.set_pipeline(fn)
        p = self.ctl('begin')
        self.assertIn('枝の工程', p.stderr)
        self.assertIn(json.loads((self.loop / 'pipeline.json').read_text())['steps'][2]['id'], p.stderr)

    def test_未完了があれば残りを名指しして続けさせる(self):
        self.ctl('begin')
        out = self.stop()
        self.assertEqual(out['decision'], 'block')
        self.assertIn('requirements', out['reason'])

    def test_催促の回数を実行の中で積み上げる(self):
        self.ctl('begin')
        self.stop()
        self.ctl('start', 'requirements')  # 状態が進んで数え直しても、合計は減らない
        self.stop()
        self.assertEqual(self.state()['nudges_total'], 2)

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
        self.ctl('begin')
        self.assertEqual(self.sub('dev-implement', '実装しました。次はテストを書きます。')['decision'], 'block')
        self.assertIsNone(self.sub('dev-implement', '実装しました。', active=True))
        self.assertIsNone(self.sub('dev-implement', 'やったこと\nSTATUS: done\n成果物: src/a.ts'))

    def test_ループ外のサブエージェントには口を出さない(self):
        self.assertIsNone(self.sub('Explore', '調べました'))

    def test_判断役はJSONで返せば通す(self):
        self.ctl('begin')
        self.assertIsNone(self.sub('gate-judge', '{"answers": []}'))
        self.assertEqual(self.sub('gate-judge', 'yesだと思います')['decision'], 'block')

    # --- 別PCからの改善案（2026-09-25）の再現 ---

    def set_pipeline(self, fn):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        fn(cfg)
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))

    # --- 人に選んでもらう問い・人待ちの一覧・まとめての答え ---

    def ask(self, *extra):
        self.ctl('begin')
        self.ctl('start', 'requirements')
        return self.ctl('block', 'requirements', '仕様が2通りに読める', '--ask', 'ログインの失敗回数の上限はどちらか',
                        '--options', 'A', 'B', '--recommend', 'A', *extra)

    def rows(self):
        return [json.loads(l) for l in (self.loop / 'judge/judgments.jsonl').read_text().splitlines()]

    def test_工程役の問いは選択肢と推奨ごと記録し人の答えを残す(self):
        self.ask('--judge-answer', 'B', '--confidence', '0.6')
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'blocked')
        self.assertEqual(s['open_asks'][0]['options'], ['A', 'B'])
        out = self.ctl('pending').stdout
        self.assertIn('ログインの失敗回数の上限', out)
        self.assertIn('推奨: A', out)
        self.assertIn('判断役: B', out)
        self.ctl('answer', 'requirements=B', '--note', '規約の3条')
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'in_progress')
        self.assertEqual(s['answered'][-1]['answer'], 'B')
        r = self.rows()[-1]
        self.assertEqual((r['kind'], r['recommend'], r['answer'], r['human_answer']), ('ask', 'A', 'B', 'B'))

    def test_1工程に問いを複数並べ番号でまとめて答えられる(self):
        self.ask('--context', '規約は3回、画面の文言は5回と書いている')
        self.ctl('block', 'requirements', '別の論点', '--ask', 'ロックの解除は誰がするか',
                 '--options', '本人', '管理者', '--recommend', '管理者')
        s = self.state()['steps']['requirements']
        self.assertEqual([k['question'] for k in s['open_asks']],
                         ['ログインの失敗回数の上限はどちらか', 'ロックの解除は誰がするか'])
        out = self.ctl('pending').stdout
        self.assertIn('requirements#1', out)
        self.assertIn('requirements#2', out)
        self.assertIn('背景: 規約は3回', out)
        p = self.ctl('answer', 'requirements=A', ok=False)
        self.assertIn('requirements#1=<選択肢>', p.stderr)
        out = self.ctl('answer', 'requirements#2=本人').stdout
        self.assertIn('問い「ロックの解除は誰がするか」→ 答え「本人」', out)
        self.assertIn('残りの問い1件', out)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'blocked')
        self.assertIn('requirements（工程役の問い）', self.ctl('pending').stdout)  # 残り1つなら番号なしで答えられる
        self.ctl('answer', '--recommended')
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'in_progress')
        self.assertEqual([x['answer'] for x in s['answered']], ['本人', 'A'])
        self.assertEqual([r['human_answer'] for r in self.rows()[-2:]], ['A', '本人'])

    def test_1問だった頃の状態も読める(self):
        self.ask()
        st = self.state()
        s = st['steps']['requirements']
        s['ask'] = dict(s.pop('open_asks')[0])
        (self.loop / 'state.json').write_text(json.dumps(st, ensure_ascii=False))
        self.assertIn('ログインの失敗回数', self.ctl('pending').stdout)
        self.ctl('answer', 'requirements=A')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')

    def test_着手で工程ごとの一時置き場を作りbeginで消す(self):
        self.ctl('begin')
        out = self.ctl('start', 'requirements').stdout
        tmp = self.loop / 'tmp/requirements/main'
        self.assertTrue(tmp.is_dir())
        self.assertIn('.claude/loop/tmp/requirements/main', out)
        (tmp / 'x.txt').write_text('前の実行の実測')
        self.ctl('finish')
        self.ctl('begin')
        self.assertFalse((self.loop / 'tmp').exists())

    def test_推奨どおりの答えもどれを選んだかが残る(self):
        self.ask()
        self.ctl('answer', '--recommended')
        self.assertEqual(self.rows()[-1]['human_answer'], 'A')
        self.assertIn('人の答え', self.state()['steps']['requirements']['notes'][-1]['text'])

    def test_選択肢の外の答えは受け付けず何も変えない(self):
        self.ask()
        p = self.ctl('answer', 'requirements=C', ok=False)
        self.assertIn('選択肢に C はありません', p.stderr)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'blocked')

    def test_判断役の人待ちもまとめて答えられる(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.6}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        pend = json.loads(self.ctl('pending', '--json').stdout)
        self.assertEqual((pend[0]['kind'], pend[0]['recommend']), ('judge', 'pass'))
        self.ctl('answer', '--recommended')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'done')
        self.assertEqual(self.rows()[-1]['human_answer'], 'yes')

    def test_人の裁定は誤りの例と並べて判断役に見せる(self):
        self.ask()
        self.ctl('answer', 'requirements=B', '--note', '規約の3条')
        self.ctl('calibrate', '--apply')
        lessons = (self.loop / 'judge/lessons.md').read_text()
        self.assertIn('人の裁定', lessons)
        self.assertIn('人の答えは`B`', lessons)

    def test_較正で閾値が出た問いは判断役の答えで止めずに進める(self):
        (self.loop / 'judge').mkdir(exist_ok=True)
        (self.loop / 'judge/calibration.json').write_text(json.dumps({'thresholds': {'ask:requirements': 0.8}}))
        self.set_pipeline(lambda c: c['judge'].__setitem__('audit_rate', 0))
        p = self.ask('--judge-answer', 'A', '--confidence', '0.9')
        self.assertIn('判断役の答え A で進めます', p.stdout)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')
        self.assertEqual(self.rows()[-1]['decision'], 'auto_answer')

    def test_理由だけの停止には答えられずunblockを案内する(self):
        self.ctl('begin')
        self.ctl('block', 'requirements', '外部の返事待ち')
        p = self.ctl('answer', 'requirements=A', ok=False)
        self.assertIn('unblock', p.stderr)

    # --- 時間の上限で止まった後の再開 ---

    def test_時間で止まった実行は延ばして再開できる(self):
        self.set_pipeline(lambda c: (c.__setitem__('time_budget_sec', 60), c['limits'].__setitem__('time_budget_hard', True)))
        self.ctl('begin')
        self.env['LOOP_NOW'] = '1100'
        self.stop()
        p = self.ctl('resume')
        self.assertIn('--extend', p.stdout)
        self.ctl('resume', '--extend', '3600')
        self.assertIsNone(self.stop().get('systemMessage'))
        self.assertTrue(self.state()['active'])
        self.assertIn('延長3600s', self.ctl('status').stdout)

    def test_止まった工程の後ろの工程は催促しない(self):
        self.ctl('begin')
        self.ctl('block', 'requirements', '顧客の回答待ち')
        self.assertIsNone(self.stop())
        out = self.ctl('status').stdout
        self.assertIn('前提のrequirementsが止まっているため待ち', out)

    def test_止まった工程と切り離した工程は催促する(self):
        self.set_pipeline(lambda c: c['steps'][3].__setitem__('after', []))
        self.ctl('begin')
        self.ctl('block', 'requirements', '顧客の回答待ち')
        out = self.stop()
        self.assertEqual(out['decision'], 'block')
        self.assertIn('test', out['reason'])
        self.assertNotIn('design', out['reason'])

    def test_ゲートの差し戻し理由に不合格の項目が残る(self):
        self.ctl('begin')
        self.ctl('start', 'requirements')
        self.ctl('submit', 'requirements')
        self.ctl('review', 'requirements', 'pass')
        self.ctl('gate', 'requirements', ok=False)
        notes = self.state()['steps']['requirements']['notes']
        self.assertIn('requirements.md が無いか空', notes[-1]['text'])
        self.assertNotIn('✖の項目を直してください', notes[-1]['text'])

    def run_test_gate(self, report):
        (self.loop / 'gates/commands.env').write_text('TEST_CMD="true"\n')
        self.write_requirements()
        if report is not None:
            (self.root / 'docs/loop/test-report.md').write_text(report)
        env = dict(self.env, LOOP_STEP='test', REPO_ROOT=str(self.root))
        return subprocess.run(['bash', str(self.loop / 'gates/test.sh')], capture_output=True, text=True, env=env)

    def test_テスト報告の失敗0件は通る(self):
        p = self.run_test_gate('# テスト報告\n失敗 0件\n\n| 要件 | テスト | 結果 |\n|---|---|---|\n| REQ-01 | test_login | 合格 |\n')
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_テスト報告の結果が不合格なら落ちる(self):
        p = self.run_test_gate('| 要件 | テスト | 結果 |\n|---|---|---|\n| REQ-01 | test_login | 不合格 |\n')
        self.assertEqual(p.returncode, 1)
        self.assertIn('REQ-01', p.stdout)

    def test_テスト報告のidは語の境界で照合する(self):
        (self.root / 'docs/loop').mkdir(parents=True, exist_ok=True)
        p = self.run_test_gate('| 要件 | テスト | 結果 |\n|---|---|---|\n| REQ-011 | test_x | 合格 |\n')
        self.assertEqual(p.returncode, 1)
        self.assertIn('REQ-01 の行が表に無い', p.stdout)

    def test_idの網羅は部分一致で満たさない(self):
        (self.root / 'a.md').write_text('opt\nREQ-01\n')
        (self.root / 'b.md').write_text('options\nREQ-01の確認\n')
        env = dict(self.env, LOOP_STEP='x', REPO_ROOT=str(self.root))
        script = '. "$LOOP_DIR/gates/lib.sh"; need_all_ids a.md b.md "opt|REQ-[0-9]+"; gate_end'
        p = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn('無いid: opt', p.stdout)
        self.assertNotIn('REQ-01 ', p.stdout.split('無いid:')[1])
        sys.path.insert(0, str(self.loop / 'bin'))
        import rules
        ok, msg = rules.evaluate({'kind': 'need_all_ids', 'args': ['a.md', 'b.md', 'opt|REQ-[0-9]+']}, self.root)
        self.assertFalse(ok)
        self.assertEqual(msg, 'b.md に無いid: opt')

    def test_ゲートの空打ちは状態も記録も変えない(self):
        self.ctl('begin')
        p = self.ctl('gate', 'requirements', '--dry-run', ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn('--dry-run', p.stdout)
        self.assertEqual(self.state()['steps']['requirements']['status'], 'pending')
        self.assertFalse((self.loop / 'stats/gates.jsonl').exists())
        self.write_requirements()
        self.assertEqual(self.ctl('gate', 'requirements', '--dry-run').returncode, 0)

    def test_閉じた実行の人待ちは閉じた実行の残りと出る(self):
        self.ctl('begin')
        self.ctl('block', 'requirements', '外部の返事待ち')
        self.ctl('finish')
        self.assertIn('閉じた実行', self.ctl('pending').stdout)
        self.assertIn('閉じた実行の残り', self.ctl('status').stdout)

    def test_テスト報告に表が無ければ落ちる(self):
        p = self.run_test_gate('REQ-01 は確かめました。合格です。\n')
        self.assertEqual(p.returncode, 1)

    def test_止まった工程や提出済みの工程には着手できない(self):
        self.ctl('begin')
        self.ctl('start', 'requirements')
        self.ctl('submit', 'requirements')
        p = self.ctl('start', 'requirements', ok=False)
        self.assertIn('reopen', p.stderr)
        self.ctl('block', 'requirements', 'x')
        p = self.ctl('start', 'requirements', ok=False)
        self.assertIn('unblock', p.stderr)

    def test_再開すると止めた理由が消え状態表にも出る(self):
        self.ctl('begin')
        for _ in range(4):
            self.stop()
        self.assertIn('止めました', self.ctl('status').stdout)
        self.ctl('resume')
        self.assertNotIn('halted', self.state())

    def test_人の判断は前方一致する別工程の記録に付かない(self):
        self.to_judge()
        run = self.state()['run_id']
        other = {'id': f'{run}-requirements-x-q-r0', 'run': run, 'step': 'requirements-x', 'question': 'q',
                 'answer': 'yes', 'confidence': 0.5, 'decision': 'escalate', 'human_answer': None}
        with open(self.loop / 'judge/judgments.jsonl', 'a') as fh:
            fh.write(json.dumps(other) + '\n')
        self.ctl('judge', 'requirements', '--answers', json.dumps({'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.5}]}))
        self.ctl('decide', 'requirements', 'pass')
        rows = [json.loads(l) for l in (self.loop / 'judge/judgments.jsonl').read_text().splitlines()]
        self.assertIsNone([r for r in rows if r['step'] == 'requirements-x'][0]['human_answer'])
        self.assertEqual([r for r in rows if r['step'] == 'requirements'][0]['human_answer'], 'yes')

    def test_報告の形はループの実行中だけ求める(self):
        msg = '実装しました。'
        self.assertIsNone(self.sub('dev-implement', msg))
        self.ctl('begin')
        self.ctl('pause')
        self.assertEqual(self.sub('dev-implement', msg)['decision'], 'block')
        self.ctl('finish')
        self.assertIsNone(self.sub('dev-implement', msg))

    # --- 判断役から決定論への昇格 ---

    def rules(self):
        f = self.loop / 'judge/rules.json'
        return json.loads(f.read_text())['rules'] if f.exists() else []

    def judge_no(self, cand, conf=0.95):
        ans = {'answers': [{'id': 'req-intent', 'answer': 'no', 'confidence': conf, 'reason': '節が無い', 'rule_candidate': cand}]}
        return self.ctl('judge', 'requirements', '--answers', json.dumps(ans))

    def test_不合格の機械的な理由はルールの候補として影で走り始める(self):
        self.to_judge()
        self.judge_no({'kind': 'need_match', 'args': ['docs/loop/requirements.md', '^## スコープ外']})
        rs = self.rules()
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0]['status'], 'shadow')
        row = json.loads((self.loop / 'judge/judgments.jsonl').read_text().splitlines()[0])
        self.assertTrue(row['shadow'][rs[0]['id']])

    def test_形の誤った候補とリポの外を指す候補は捨てる(self):
        self.to_judge()
        self.judge_no({'kind': 'need_file', 'args': ['../etc/passwd']})
        self.assertEqual(self.rules(), [])
        self.assertIn('候補を捨てた', self.state()['steps']['requirements']['notes'][-3]['text'])

    def test_合格の答えに添えた候補は使わない(self):
        self.to_judge()
        ans = {'answers': [{'id': 'req-intent', 'answer': 'yes', 'confidence': 0.99,
                            'rule_candidate': {'kind': 'need_file', 'args': ['x.md']}}]}
        self.ctl('judge', 'requirements', '--answers', json.dumps(ans))
        self.assertEqual(self.rules(), [])

    def seed_rule(self, rid, check, rows):
        (self.loop / 'judge').mkdir(exist_ok=True)
        (self.loop / 'judge/rules.json').write_text(json.dumps({'rules': [
            {'id': rid, 'step': 'requirements', 'question': 'req-intent', 'check': check, 'status': 'shadow'}]}))
        with open(self.loop / 'judge/judgments.jsonl', 'w') as fh:
            for i, (fired, decision, human) in enumerate(rows):
                fh.write(json.dumps({'id': f'j{i}', 'run': 'r', 'step': 'requirements', 'question': 'req-intent',
                                     'pass_answer': 'yes', 'answer': 'no', 'decision': decision, 'human_answer': human,
                                     'shadow': {rid: fired}}) + '\n')

    def test_誤検出なしで正しい検出が揃えば昇格を提案し採用できる(self):
        self.seed_rule('r-1', {'kind': 'need_file', 'args': ['docs/loop/requirements.md']},
                       [(True, 'auto_fail', None)] * 4 + [(True, 'escalate', 'not:yes'), (False, 'auto_pass', None)])
        out = self.ctl('rules').stdout
        self.assertIn('正しい5', out)
        self.assertIn('promote r-1', out)
        self.ctl('promote', 'r-1')
        self.assertEqual(self.rules()[0]['status'], 'promoted')

    def test_誤検出があれば昇格を拒む(self):
        self.seed_rule('r-2', {'kind': 'need_file', 'args': ['x.md']},
                       [(True, 'auto_fail', None)] * 6 + [(True, 'escalate', 'yes')])
        out = self.ctl('rules').stdout
        self.assertIn('誤り1', out)
        self.assertIn('retire r-2', out)
        p = self.ctl('promote', 'r-2', ok=False)
        self.assertIn('条件を満たしていません', p.stderr)
        self.ctl('retire', 'r-2')
        self.assertEqual(self.rules()[0]['status'], 'retired')

    def test_人が後から訂正すると実績も変わる(self):
        self.seed_rule('r-3', {'kind': 'need_file', 'args': ['x.md']}, [(True, 'auto_fail', None)] * 5)
        self.ctl('override', 'j0', 'yes')
        self.assertIn('誤り1', self.ctl('rules').stdout)

    def test_採用したルールは決定論ゲートで効く(self):
        self.seed_rule('r-4', {'kind': 'need_match', 'args': ['docs/loop/requirements.md', '^## スコープ外']}, [])
        self.ctl('promote', 'r-4', '--force')
        self.ctl('begin')
        self.ctl('start', 'requirements'); self.ctl('submit', 'requirements'); self.ctl('review', 'requirements', 'pass')
        self.write_requirements()
        p = self.ctl('gate', 'requirements', ok=False)
        self.assertIn('✖ r-4', p.stdout)
        self.assertIn('r-4', self.state()['steps']['requirements']['notes'][-1]['text'])
        (self.root / 'docs/loop/requirements.md').write_text('# 要件\n## REQ-01 x\n受け入れ条件: y\n## スコープ外\n- なし\n')
        self.ctl('start', 'requirements'); self.ctl('submit', 'requirements'); self.ctl('review', 'requirements', 'pass')
        self.ctl('gate', 'requirements')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'judge')

    # --- 歯止め（2026-09-25: cadenceの振り返りと別PCの失敗事例から） ---

    def gate_fail_requirements(self):
        self.ctl('start', 'requirements'); self.ctl('submit', 'requirements'); self.ctl('review', 'requirements', 'pass')
        return self.ctl('gate', 'requirements', ok=False)

    def stats_rows(self):
        f = self.loop / 'stats/gates.jsonl'
        return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []

    def test_検査ごとの合否を鍵で記録する(self):
        self.ctl('begin')
        self.gate_fail_requirements()
        rows = self.stats_rows()
        keys = {r['key']: r['ok'] for r in rows}
        self.assertFalse(keys['need_file docs/loop/requirements.md'])
        self.assertIn('forbid_match docs/loop/requirements.md TBD|TODO|要確認|\\?\\?\\?', keys)

    def test_一度も落ちない検査を外す候補に挙げる(self):
        self.set_pipeline(lambda c: c.__setitem__('sunset_min_runs', 2))
        self.ctl('begin')
        self.gate_fail_requirements()
        self.gate_fail_requirements()
        out = self.ctl('gate-stats').stdout
        self.assertIn('外す候補', out)
        cand = out.split('外す候補')[1]
        self.assertIn('forbid_match', cand)
        self.assertNotIn('need_file', cand)

    def test_実行中にループ自身が変わればゲートで落とし控え直せば通す(self):
        self.ctl('begin')
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['max_rework'] = 9
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg))
        self.write_requirements()
        p = self.gate_fail_requirements()
        self.assertIn('loop-self', p.stdout)
        self.assertIn('pipeline.json', self.state()['steps']['requirements']['notes'][-1]['text'])
        self.ctl('accept-self')
        self.ctl('start', 'requirements'); self.ctl('submit', 'requirements'); self.ctl('review', 'requirements', 'pass')
        self.ctl('gate', 'requirements')

    def test_実行全体の差し戻しの上限で止まる(self):
        self.set_pipeline(lambda c: c['limits'].__setitem__('max_total_rework', 1))
        self.ctl('begin')
        for _ in range(2):
            self.ctl('start', 'requirements'); self.ctl('submit', 'requirements')
            self.ctl('review', 'requirements', 'fail')
        p = self.ctl('start', 'requirements', ok=False)
        self.assertIn('実行全体の差し戻しが上限', p.stderr)
        st = self.state()
        self.assertFalse(st['active'])
        self.assertIn('上限', st['halted'])

    def test_分担の数の上限で止まる(self):
        self.set_pipeline(lambda c: c['limits'].__setitem__('max_shards', 0))
        self.ctl('begin')
        self.ctl('start', 'requirements', '--shard', 'a')
        p = self.ctl('start', 'requirements', '--shard', 'b', ok=False)
        self.assertIn('分担の数が上限', p.stderr)

    def test_工程ごとの最初の着手は分担の上限に数えない(self):
        # 問いごとに工程を回す実行（工程の数が上限を超える）でも、1工程1分担なら止まらない
        self.set_pipeline(lambda c: c['limits'].__setitem__('max_shards', 0))
        self.ctl('begin')
        self.ctl('start', 'requirements')
        self.assertTrue(self.state()['active'])
        self.assertEqual(self.state()['shards_started'], 0)

    def test_着手前の確かめが通らなければ工程を止め工程役を起こさせない(self):
        pc = self.loop / 'gates/precheck.sh'
        pc.write_text('echo "  ✖ ログインの残りが30分（見込みは60分）"; exit 1\n')
        self.set_pipeline(lambda c: c['steps'][0].__setitem__('precheck', 'gates/precheck.sh'))
        self.ctl('begin')
        p = self.ctl('start', 'requirements', ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertIn('ログインの残りが30分', p.stderr)
        s = self.state()['steps']['requirements']
        self.assertEqual(s['status'], 'blocked')
        self.assertIn('着手前の確かめ', s['blocker'])
        pc.write_text('exit 0\n')  # 人が前提を直した
        self.ctl('unblock', 'requirements')
        self.ctl('start', 'requirements')
        self.assertEqual(self.state()['steps']['requirements']['status'], 'in_progress')

    def test_時間の上限を打ち切りにするとStopフックが止める(self):
        self.set_pipeline(lambda c: (c.__setitem__('time_budget_sec', 60), c['limits'].__setitem__('time_budget_hard', True)))
        self.ctl('begin')
        self.env['LOOP_NOW'] = '1100'
        out = self.stop()
        self.assertIn('時間の上限', out['systemMessage'])
        self.assertFalse(self.state()['active'])

    def test_時間の予算は既定では打ち切りにしない(self):
        self.set_pipeline(lambda c: c.__setitem__('time_budget_sec', 60))
        self.ctl('begin')
        self.env['LOOP_NOW'] = '1100'
        out = self.stop()
        self.assertEqual(out['decision'], 'block')
        self.assertIn('elapsed 100s / 60s', out['reason'])

    def test_採用中のルールは工程あたりの上限を超えて足せない(self):
        (self.loop / 'judge').mkdir(exist_ok=True)
        rs = [{'id': f'r-{i}', 'step': 'requirements', 'question': 'req-intent',
               'check': {'kind': 'need_file', 'args': [f'f{i}.md']}, 'status': 'promoted' if i < 3 else 'shadow'} for i in range(4)]
        (self.loop / 'judge/rules.json').write_text(json.dumps({'rules': rs}))
        p = self.ctl('promote', 'r-3', ok=False)
        self.assertIn('上限', p.stderr)
        self.ctl('promote', 'r-3', '--force')

    def test_採用後に一度も落とさないルールは外す候補に挙げる(self):
        self.set_pipeline(lambda c: c.__setitem__('sunset_min_runs', 1))
        (self.loop / 'judge').mkdir(exist_ok=True)
        (self.loop / 'judge/rules.json').write_text(json.dumps({'rules': [
            {'id': 'r-9', 'step': 'requirements', 'question': 'req-intent',
             'check': {'kind': 'need_match', 'args': ['docs/loop/requirements.md', 'REQ']}, 'status': 'promoted'}]}))
        self.ctl('begin')
        self.write_requirements()
        self.ctl('start', 'requirements'); self.ctl('submit', 'requirements'); self.ctl('review', 'requirements', 'pass')
        self.ctl('gate', 'requirements')
        self.assertIn('外す候補', self.ctl('rules').stdout)

    def test_設計の工程は作らない選択肢を問う(self):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        q = [s for s in cfg['steps'] if s['id'] == 'design'][0]['judge_questions'][0]
        self.assertEqual(q['id'], 'design-needed')
        self.assertIn('remove', q['answers'])


class ScopeGateTest(unittest.TestCase):
    """実装のゲートの範囲の検査（本物のgitリポで）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        g = lambda *a: subprocess.run(['git', '-C', str(self.root), *a], capture_output=True, text=True, check=True)
        self.git = g
        g('init', '-q'); g('config', 'user.email', 't@t'); g('config', 'user.name', 't')
        (self.root / 'src').mkdir()
        (self.root / 'src/a.py').write_text('a\n')
        (self.root / 'README.md').write_text('r\n')
        g('add', '-A'); g('commit', '-qm', 'init')
        scaffold(self.root, '--profile', 'dev', '--no-settings')
        self.loop = self.root / '.claude/loop'
        self.env = dict(os.environ, LOOP_DIR=str(self.loop))
        subprocess.run([sys.executable, str(self.loop / 'bin/loopctl.py'), 'begin'], env=self.env, check=True, capture_output=True)
        d = self.root / 'docs/loop'
        d.mkdir(parents=True)
        (d / 'design.md').write_text('# 設計\n## 触ってよいファイル\n- `src/*`\n- tests/test_a.py\n## 実装の分担\n')

    def tearDown(self):
        self._tmp.cleanup()

    def scope(self):
        base = json.loads((self.loop / 'state.json').read_text())['base_commit']
        env = dict(self.env, LOOP_STEP='implement', REPO_ROOT=str(self.root), LOOP_BASE_COMMIT=base or '')
        script = '. "$LOOP_DIR/gates/lib.sh"; need_scope docs/loop/design.md "触ってよいファイル"; gate_end'
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)

    def test_開始時のコミットを記録する(self):
        self.assertTrue(json.loads((self.loop / 'state.json').read_text())['base_commit'])

    def test_範囲内の変更と新規ファイルは通す(self):
        (self.root / 'src/a.py').write_text('b\n')
        (self.root / 'src/sub').mkdir()
        (self.root / 'src/sub/new.py').write_text('n\n')
        (self.root / 'tests').mkdir()
        (self.root / 'tests/test_a.py').write_text('t\n')
        p = self.scope()
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_範囲外の変更は落とす(self):
        (self.root / 'README.md').write_text('changed\n')
        p = self.scope()
        self.assertEqual(p.returncode, 1)
        self.assertIn('範囲外の変更: README.md', p.stdout)

    def test_範囲外の新規ファイルも落とす(self):
        (self.root / 'other.txt').write_text('x\n')
        self.assertIn('範囲外の変更: other.txt', self.scope().stdout)

    def test_開始時に既にあった未コミットの変更は数えない(self):
        # setUpでひな型を入れたまま（未コミット）で begin している
        self.assertIn('.claude/agents/dev-design.md', json.loads((self.loop / 'state.json').read_text())['base_preexisting'])
        self.assertNotIn('dev-design.md', self.scope().stdout)

    def test_一覧が無ければ落とす(self):
        (self.root / 'docs/loop/design.md').write_text('# 設計\n')
        self.assertIn('一覧が無い', self.scope().stdout)

    def lib(self, body):
        base = json.loads((self.loop / 'state.json').read_text())['base_commit']
        env = dict(self.env, LOOP_STEP='x', REPO_ROOT=str(self.root), LOOP_BASE_COMMIT=base or '')
        return subprocess.run(['bash', '-c', '. "$LOOP_DIR/gates/lib.sh"; ' + body + '; gate_end'],
                              capture_output=True, text=True, env=env)

    def test_触ってはいけない場所の変更を落とす(self):
        self.assertEqual(self.lib("forbid_paths '^README\\.md$' 説明書").returncode, 0)
        (self.root / 'README.md').write_text('changed\n')
        p = self.lib("forbid_paths '^README\\.md$' 説明書")
        self.assertEqual(p.returncode, 1)
        self.assertIn('触ってはいけない場所が変わった（説明書）: README.md', p.stdout)

    def test_触ってはいけない場所の新規ファイルも落とし開始時の変更は数えない(self):
        (self.root / 'data').mkdir()
        (self.root / 'data/gen.json').write_text('{}\n')
        self.assertIn('data/gen.json', self.lib("forbid_paths '^data/'").stdout)
        self.assertEqual(self.lib("forbid_paths '^\\.claude/'").returncode, 0)  # ループ自身は数えない

    def test_コミットのゲートは未コミットの変更を落とす(self):
        self.git('add', '-A'); self.git('commit', '-qm', 'ひな型')
        p = subprocess.run(['bash', str(self.loop / 'gates/commit.sh')], capture_output=True, text=True,
                           env=dict(self.env, LOOP_STEP='commit', REPO_ROOT=str(self.root)))
        self.assertEqual(p.returncode, 0, p.stdout)
        (self.root / 'src/a.py').write_text('dirty\n')
        p = subprocess.run(['bash', str(self.loop / 'gates/commit.sh')], capture_output=True, text=True,
                           env=dict(self.env, LOOP_STEP='commit', REPO_ROOT=str(self.root)))
        self.assertEqual(p.returncode, 1)
        self.assertIn('未コミットの変更が残っている', p.stdout)

    def test_push済みを求める指定では上流が無ければ落とす(self):
        self.git('add', '-A'); self.git('commit', '-qm', 'ひな型')
        p = subprocess.run(['bash', str(self.loop / 'gates/commit.sh')], capture_output=True, text=True,
                           env=dict(self.env, LOOP_STEP='commit', REPO_ROOT=str(self.root), PUSH_REQUIRED='1'))
        self.assertEqual(p.returncode, 0, p.stdout)  # commands.env の空の値が環境の値を上書きする
        env_f = self.loop / 'gates/commands.env'
        env_f.write_text(env_f.read_text().replace('PUSH_REQUIRED=""', 'PUSH_REQUIRED="1"'))
        p = subprocess.run(['bash', str(self.loop / 'gates/commit.sh')], capture_output=True, text=True,
                           env=dict(self.env, LOOP_STEP='commit', REPO_ROOT=str(self.root)))
        self.assertEqual(p.returncode, 1)
        self.assertIn('上流のブランチが無い', p.stdout)

    def test_push済みはHEADが上流に含まれれば通す(self):
        self.git('add', '-A'); self.git('commit', '-qm', 'ひな型')
        remote = Path(self._tmp.name + '-remote.git')
        self.addCleanup(shutil.rmtree, remote, True)
        subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-q', '-u', 'origin', 'HEAD')
        # ほかのメンバーが後からpushした（上流がHEADより先へ進んだ）
        other = Path(self._tmp.name + '-other')
        self.addCleanup(shutil.rmtree, other, True)
        subprocess.run(['git', 'clone', '-q', str(remote), str(other)], check=True)
        for a in (['config', 'user.email', 't@t'], ['config', 'user.name', 't'], ['commit', '-q', '--allow-empty', '-m', 'x'], ['push', '-q']):
            subprocess.run(['git', '-C', str(other), *a], check=True, capture_output=True)
        env = dict(self.env, LOOP_STEP='commit', REPO_ROOT=str(self.root))
        script = '. "$LOOP_DIR/gates/lib.sh"; need_pushed; gate_end'
        p = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.git('commit', '-q', '--allow-empty', '-m', 'まだpushしていない')
        p = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn('push されていない', p.stdout)


class SharedTreeGuardTest(unittest.TestCase):
    """PreToolUseフック: 実行中の工程役・レビュー役が共有の作業ツリーを巻き戻す git を止める（本物のgitリポで）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        g = lambda *a: subprocess.run(['git', '-C', str(self.root), *a], capture_output=True, text=True, check=True)
        g('init', '-q'); g('config', 'user.email', 't@t'); g('config', 'user.name', 't')
        (self.root / 'a.txt').write_text('a\n')
        (self.root / 'sub').mkdir()
        g('add', '-A'); g('commit', '-qm', 'init')
        scaffold(self.root, '--profile', 'dev', '--no-settings')
        self.loop = self.root / '.claude/loop'
        self.env = dict(os.environ, LOOP_DIR=str(self.loop))
        self.other = Path(self._tmp.name + '-wt')
        g('worktree', 'add', '-q', str(self.other), 'HEAD')

    def tearDown(self):
        shutil.rmtree(self.other, ignore_errors=True)
        self._tmp.cleanup()

    def ctl(self, *args):
        subprocess.run([sys.executable, str(self.loop / 'bin/loopctl.py'), *args], env=self.env, check=True, capture_output=True)

    def denied(self, cmd, agent='dev-implement', cwd=None):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': cmd},
                   'cwd': str(cwd or self.root), 'agent_type': agent}
        p = subprocess.run([sys.executable, str(self.loop / 'bin/shared-tree-guard.py')], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env, cwd=self.root)
        self.assertEqual(p.returncode, 0, p.stderr)
        return bool(p.stdout.strip()) and json.loads(p.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'

    def test_実行中の工程役とレビュー役の巻き戻しを止める(self):
        self.ctl('begin')
        for cmd in ('git stash', 'git checkout -- a.txt', 'npm test && git reset --hard', 'git restore a.txt',
                    'cd sub; git -C .. clean -fd', 'X=1 git switch main'):
            self.assertTrue(self.denied(cmd), cmd)
        self.assertTrue(self.denied('git stash', agent='review-implement'))

    def test_読むだけの操作と外の作業ツリーは通す(self):
        self.ctl('begin')
        for cmd in ('git stash list', 'git diff', 'git show HEAD:a.txt', 'git restore --staged a.txt',
                    f'git worktree add {self.other}-x HEAD', f'git -C {self.other} checkout -- a.txt',
                    f'cd {self.other} && git stash', 'echo "git stash"'):
            self.assertFalse(self.denied(cmd), cmd)

    def test_実行の外と統括役とループ外のエージェントには口を出さない(self):
        self.assertFalse(self.denied('git stash'))  # 実行が無い
        self.ctl('begin')
        self.assertFalse(self.denied('git stash', agent='loop-conductor'))
        self.assertFalse(self.denied('git stash', agent=''))
        self.assertFalse(self.denied('git stash', agent='Explore'))
        self.ctl('finish')
        self.assertFalse(self.denied('git stash'))


class PerItemTest(unittest.TestCase):
    """per_item: 項目の一覧 × 工程の型を begin で展開し、項目ごとに独立して止まる。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / '.git').mkdir()
        scaffold(self.root, '--profile', 'generic', '--no-settings')
        self.loop = self.root / '.claude/loop'
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['steps'] = [dict(cfg['steps'][0], id='triage', outputs=['loop-out/triage.md'])]
        cfg['steps'].append({'id': 'report', 'worker': 'step-worker', 'reviewer': None, 'gate': None,
                             'after': ['*/fix'], 'judge_questions': []})
        cfg['per_item'] = {'after': ['triage'], 'items': ['q1'], 'steps': [
            {'id': 'decide', 'worker': 'step-worker', 'reviewer': None, 'gate': 'gates/outputs.sh',
             'instructions': '{item} について決める', 'outputs': ['loop-out/{item}/decide.md'], 'judge_questions': [
                 {'id': 'grounded', 'question': '{item} の決定に根拠があるか', 'answers': ['yes', 'no'], 'pass': 'yes'}]},
            {'id': 'fix', 'worker': 'step-worker', 'reviewer': None, 'gate': None, 'judge_questions': []}]}
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))
        self.env = dict(os.environ, LOOP_DIR=str(self.loop), LOOP_NOW='1000')

    def tearDown(self):
        self._tmp.cleanup()

    def ctl(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(self.loop / 'bin/loopctl.py'), *args],
                           capture_output=True, text=True, env=self.env, cwd=self.root)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p


    def test_固定工程の終端は項目ごとの工程が後ろに付いても枝と知らせない(self):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['per_item']['items'] = ['q1', 'q2']  # report が2つを待つ集約になる
        cfg['steps'].append({'id': 'cleanup', 'worker': 'step-worker', 'reviewer': None, 'gate': None,
                             'after': ['report'], 'judge_questions': []})
        cfg['steps'].insert(1, {'id': 'followup', 'worker': 'step-worker', 'reviewer': None, 'gate': None,
                                'after': ['triage'], 'judge_questions': []})
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))
        err = self.ctl('begin').stderr
        self.assertIn('枝の工程があります: followup。', err)
        self.assertNotIn('cleanup', err.split('。')[0])

    def test_直列の項目でも全項目の枝を知らせる(self):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['per_item']['items'] = ['q1', 'q2', 'q3']
        cfg['per_item']['serial'] = True
        cfg['per_item']['steps'].append({'id': 'followup', 'worker': 'step-worker', 'reviewer': None,
                                         'gate': None, 'after': ['decide'], 'judge_questions': []})
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))
        # 直列化で q2/decide・q3/decide は前提2つ（triage＋前の項目の最後）になるが、集約とは見なさない
        err = self.ctl('begin').stderr
        # 次の項目が順番のために待つだけの q1/followup・q2/followup も、結果は report に入らない
        self.assertIn('枝の工程があります: q1/followup, q2/followup, q3/followup。', err)
    def state(self):
        return json.loads((self.loop / 'state.json').read_text())

    def done(self, step):
        self.ctl('start', step)
        self.ctl('submit', step)

    def test_項目ごとに工程を展開し型の中身を置き換える(self):
        self.ctl('begin', '--items', 'q1', 'q2')
        self.assertIn('q2/decide', self.state()['steps'])
        d = json.loads(self.ctl('show', 'q2/decide').stdout)
        self.assertEqual(d['instructions'], 'q2 について決める')
        self.assertEqual(d['outputs'], ['loop-out/q2/decide.md'])
        self.assertEqual(d['judge_questions'][0]['id'], 'grounded')
        self.assertEqual(d['after'], ['triage'])

    def test_項目ごとに独立して止まり他の項目は進む(self):
        self.ctl('begin', '--items', 'q1', 'q2')
        (self.root / 'loop-out').mkdir()
        (self.root / 'loop-out/triage.md').write_text('仕分け\n')
        self.done('triage'); self.ctl('review', 'triage', 'pass'); self.ctl('gate', 'triage')
        self.ctl('start', 'q1/decide')
        self.ctl('block', 'q1/decide', '人の裁定が要る')
        (self.root / 'loop-out/q2').mkdir()
        (self.root / 'loop-out/q2/decide.md').write_text('決めた\n')
        self.done('q2/decide')
        self.ctl('gate', 'q2/decide')
        self.assertEqual(self.state()['steps']['q2/decide']['status'], 'judge')
        ready = [x['id'] for x in json.loads(self.ctl('next').stdout)]
        self.assertNotIn('q1/fix', ready)
        self.assertNotIn('report', ready)  # 全項目の fix を待つ

    def test_実行中に項目を足してもループ自身は変わらない(self):
        self.ctl('begin')
        before = (self.loop / 'pipeline.json').read_bytes()
        self.ctl('add-item', 'q3')
        self.assertEqual(self.state()['items'], ['q1', 'q3'])
        self.assertEqual(self.state()['steps']['q3/decide']['status'], 'pending')
        self.assertEqual((self.loop / 'pipeline.json').read_bytes(), before)

    def test_項目idの形と数の上限を確かめる(self):
        self.assertIn('使えない文字', self.ctl('begin', '--items', 'a b', ok=False).stderr)
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['limits']['max_items'] = 1
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))
        self.assertIn('max_items', self.ctl('begin', '--items', 'a', 'b', ok=False).stderr)
        self.ctl('begin', '--items', 'a')
        self.assertIn('max_items', self.ctl('add-item', 'b', ok=False).stderr)

    def test_ルールの候補は項目をまたいで同じ型で育つ(self):
        self.ctl('begin', '--items', 'q1', 'q2')
        st = self.state()
        for sid in ('triage',):
            st['steps'][sid]['status'] = 'done'
        for it in ('q1', 'q2'):
            st['steps'][f'{it}/decide']['status'] = 'judge'
        (self.loop / 'state.json').write_text(json.dumps(st))
        for it in ('q1', 'q2'):
            ans = {'answers': [{'id': 'grounded', 'answer': 'no', 'confidence': 0.99, 'reason': '節が無い',
                                'rule_candidate': {'kind': 'need_match', 'args': [f'loop-out/{it}/decide.md', '^## 根拠']}}]}
            self.ctl('judge', f'{it}/decide', '--answers', json.dumps(ans))
        rules = json.loads((self.loop / 'judge/rules.json').read_text())['rules']
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]['step'], 'decide')
        self.assertEqual(rules[0]['check']['args'][0], 'loop-out/{item}/decide.md')


class PerItemOrderTest(PerItemTest):
    """per_item の順番（serial）・一覧のファイル・0件の扱い。"""

    def set_pi(self, **kw):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['per_item'].update(kw)
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))

    def finish_triage(self):
        st = self.state()
        st['steps']['triage']['status'] = 'done'
        (self.loop / 'state.json').write_text(json.dumps(st))

    def test_順番に回す指定では次の1件だけを返し順番を守らせる(self):
        self.set_pi(serial=True)
        self.ctl('begin', '--items', 'q1', 'q2', 'q3')
        self.finish_triage()
        self.assertEqual([x['id'] for x in json.loads(self.ctl('next').stdout)], ['q1/decide'])
        self.assertIn('q1/fix', self.ctl('start', 'q2/decide', ok=False).stderr)
        st = self.state()
        for sid in ('q1/decide', 'q1/fix'):
            st['steps'][sid]['status'] = 'done'
        (self.loop / 'state.json').write_text(json.dumps(st))
        self.assertEqual([x['id'] for x in json.loads(self.ctl('next').stdout)], ['q2/decide'])

    def test_順番に回す指定では前の項目が止まれば後ろは待つ(self):
        self.set_pi(serial=True)
        self.ctl('begin', '--items', 'q1', 'q2')
        self.finish_triage()
        self.ctl('start', 'q1/decide')
        self.ctl('block', 'q1/decide', '人の裁定が要る')
        self.assertEqual(json.loads(self.ctl('next').stdout), [])

    def test_指定が無ければ項目は並べて返す(self):
        self.ctl('begin', '--items', 'q1', 'q2')
        self.finish_triage()
        self.assertEqual([x['id'] for x in json.loads(self.ctl('next').stdout)], ['q1/decide', 'q2/decide'])

    def test_一覧のファイルをpipelineに書いておけば読む(self):
        (self.root / 'items.txt').write_text('# M1のカード\nc1\nc2\n')
        self.set_pi(items_file='items.txt', items=[])
        self.ctl('begin')
        self.assertEqual(self.state()['items'], ['c1', 'c2'])
        self.ctl('begin', '--force', '--items', 'z9')  # その場で渡した一覧が優先
        self.assertEqual(self.state()['items'], ['z9'])

    def test_一覧のファイルが無ければ断る(self):
        self.set_pi(items_file='nothing.txt')
        self.assertIn('nothing.txt', self.ctl('begin', ok=False).stderr)

    def test_項目0件では始めず明示すれば始める(self):
        self.set_pi(items=[])
        self.assertIn('0件', self.ctl('begin', ok=False).stderr)
        self.ctl('begin', '--allow-empty')
        self.assertEqual(self.state()['items'], [])


class LimitAndRetroTest(PerItemTest):
    """begin --limit（実行の間だけの上限）と retro（振り返りの数字）。"""

    def test_上限をこの実行の間だけ差し替えpipelineは変えない(self):
        before = (self.loop / 'pipeline.json').read_bytes()
        self.ctl('begin', '--items', 'q1', '--limit', 'max_shards=0')
        self.ctl('start', 'triage')
        p = self.ctl('start', 'triage', '--shard', 'b', ok=False)
        self.assertIn('分担の数が上限（0）', p.stderr)
        self.assertEqual((self.loop / 'pipeline.json').read_bytes(), before)
        self.assertIn('max_shards=0', self.ctl('status').stdout)
        self.ctl('begin', '--force', '--items', 'q1')  # 次の実行には持ち越さない
        self.assertNotIn('limit_override', self.state())
        self.ctl('start', 'triage')
        self.ctl('start', 'triage', '--shard', 'b')

    def test_知らない上限の名前は断る(self):
        self.assertIn('上限の名前', self.ctl('begin', '--items', 'q1', '--limit', 'max_foo=1', ok=False).stderr)

    def test_振り返りは差し戻しの理由と催促と人待ちを数える(self):
        self.ctl('begin', '--items', 'q1', 'q2')
        (self.root / 'loop-out').mkdir()
        self.done('triage')
        self.ctl('review', 'triage', 'fail', '--note', '材料が足りない')
        self.ctl('submit', 'triage')
        self.ctl('review', 'triage', 'pass')
        self.ctl('gate', 'triage', ok=False)  # 成果物が無いので不合格
        st = self.state()
        st['nudges_total'] = 2
        (self.loop / 'state.json').write_text(json.dumps(st))
        d = json.loads(self.ctl('retro', '--json').stdout)
        self.assertEqual(d['rework_total'], 2)
        self.assertEqual(d['rework_by_kind'], {'レビュー': 1, '決定論ゲート': 1})
        self.assertTrue(any('need_file loop-out/triage.md' in k for k, _ in d['rework_reasons']))
        self.assertEqual(d['nudges_total'], 2)
        self.assertEqual([x['item'] for x in d['items']], ['q1', 'q2'])
        text = self.ctl('retro').stdout
        self.assertIn('振り返り', text)
        self.assertIn('差し戻し 2回', text)
        self.assertIn('・進行中', text)
        st = self.state()
        for v in st['steps'].values():
            v['status'] = 'done'
        (self.loop / 'state.json').write_text(json.dumps(st))
        self.assertIn('・全工程完了', self.ctl('retro').stdout)


    def test_項目の経過は本線と枝の人待ちを含む全体を分けて出す(self):
        self.ctl('begin', '--items', 'q1')
        st = self.state()
        mk = lambda a, b: {'status': 'done', 'shards': {}, 'rework': 0, 'blocker': None,
                           'notes': [{'t': a, 'text': '着手 shard=main'}, {'t': b, 'text': '完了'}]}
        st['steps']['q1/decide'] = mk(100, 200)
        st['steps']['q1/fix'] = mk(200, 300)
        st['steps']['q1/ask'] = mk(250, 5000)  # 枝の人待ち
        (self.loop / 'state.json').write_text(json.dumps(st))
        x = json.loads(self.ctl('retro', '--json').stdout)['items'][0]
        self.assertEqual((x['elapsed_main'], x['elapsed']), (200, 4900))
        self.assertIn('本線200s・人待ちを含む全体4900s', self.ctl('retro').stdout)

    def test_Writeが止められる成果物の名前はbeginで知らせる(self):
        cfg = json.loads((self.loop / 'pipeline.json').read_text())
        cfg['steps'][0]['outputs'] = ['loop-out/summary.md']
        (self.loop / 'pipeline.json').write_text(json.dumps(cfg, ensure_ascii=False))
        p = self.ctl('begin', '--items', 'q1')
        self.assertIn('loop-out/summary.md', p.stderr)
        self.assertNotIn('decide.md', p.stderr)


class UpdateTest(unittest.TestCase):
    """--update: 入れた時の版と突き合わせ、手を入れていないファイルだけ新しくする。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / 'repo'
        self.root.mkdir()
        (self.root / '.git').mkdir()
        # 「入れた時の版」を作る: 今のひな型を写し、道具と工程表とエージェント1つを古い中身にする
        self.old = base / 'old'
        shutil.copytree(TOOL.parents[1] / 'templates' / 'loop', self.old)
        (self.old / 'common/.claude/loop/bin/rules.py').unlink()
        (self.old / 'common/.claude/loop/bin/loopctl.py').write_text('# 古い道具\n')
        (self.old / 'dev/.claude/loop/pipeline.json').write_text('{"old": true}\n')
        (self.old / 'dev/.claude/agents/dev-test.md').write_text('古いテスト役\n')
        # 古い版で入れた状態を再現する
        scaffold(self.root, '--profile', 'dev', '--no-settings')
        for rel in ['.claude/loop/bin/loopctl.py', '.claude/loop/pipeline.json', '.claude/agents/dev-test.md']:
            layer = 'common' if 'bin' in rel else 'dev'
            shutil.copy(self.old / layer / rel, self.root / rel)
        (self.root / '.claude/loop/bin/rules.py').unlink()
        # 利用者が手で直したファイル
        (self.root / '.claude/loop/pipeline.json').write_text('{"old": true, "mine": 1}\n')

    def tearDown(self):
        self._tmp.cleanup()

    def update(self, *args):
        return scaffold(self.root, '--update', '--old-dir', str(self.old), *args)

    def test_手を入れていないファイルは新しくし直したものは触らない(self):
        p = self.update()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('bin/rules.py', p.stdout.split('上書き')[0])
        self.assertNotIn('古い道具', (self.root / '.claude/loop/bin/loopctl.py').read_text())
        self.assertNotIn('古いテスト役', (self.root / '.claude/agents/dev-test.md').read_text())
        self.assertIn('"mine": 1', (self.root / '.claude/loop/pipeline.json').read_text())
        self.assertIn('手で直されているので触っていない: 1件', p.stdout)
        self.assertIn('templates/loop/dev/.claude/loop/pipeline.json', p.stdout)

    def test_確認だけなら何も変えない(self):
        self.update('--dry-run')
        self.assertIn('古い道具', (self.root / '.claude/loop/bin/loopctl.py').read_text())
        self.assertFalse((self.root / '.claude/loop/bin/rules.py').exists())

    def test_入れた記録が無ければ断る(self):
        (self.root / '.claude/loop/.scaffold.json').unlink()
        p = self.update()
        self.assertEqual(p.returncode, 2)

    def test_名前を付けたループも更新できる(self):
        root = Path(self._tmp.name) / 'named'
        root.mkdir()
        scaffold(root, '--profile', 'generic', '--name', 'x', '--no-settings')
        w = root / '.claude/agents/x-step-worker.md'
        w.write_text(w.read_text() + '手で足した行\n')
        c = root / '.claude/loop-x/bin/loopctl.py'
        c.write_text('# 古い\n')
        self.assertEqual(scaffold(root, '--update').returncode, 2)  # 名前なしでは見つからず、名前を案内する
        self.assertIn('--name', scaffold(root, '--update').stderr)
        p = scaffold(root, '--update', '--name', 'x')
        self.assertEqual(p.returncode, 0, p.stderr)
        # ひな型側がこの間に変わったかどうかで、差分コマンド付きの一覧か1行のまとめかに分かれる（どちらも触らない）
        self.assertIn('x-step-worker.md', p.stdout)
        self.assertIn('loop-x/bin/loopctl.py', p.stdout)
        self.assertIn('手で足した行', w.read_text())
        self.assertEqual(c.read_text(), '# 古い\n')

    def test_ひな型側が変わっていない手直しは1行にまとめる(self):
        # 入れた時の版と今の版で中身が同じファイルを手で直した場合（取り込むものが無い）
        w = self.root / '.claude/agents/dev-design.md'
        w.write_text(w.read_text() + '手で足した行\n')
        p = self.update()
        self.assertIn('手を入れてある（ひな型側の変更なし・取り込むものは無い）: 1件', p.stdout)
        self.assertNotIn('templates/loop/dev/.claude/agents/dev-design.md', p.stdout)
        self.assertIn('手で足した行', w.read_text())

    def test_リンタの設定があれば対象から外すよう知らせる(self):
        (self.root / 'pyproject.toml').write_text('[tool.ruff]\nline-length = 100\n')
        self.assertIn('extend-exclude', self.update().stdout)
        (self.root / 'pyproject.toml').write_text('[tool.ruff]\nextend-exclude = [".claude"]\n')
        self.assertNotIn('extend-exclude', self.update().stdout)

    def test_新規に入れる時はprofileが要る(self):
        p = scaffold(self.root)
        self.assertEqual(p.returncode, 2)


if __name__ == '__main__':
    unittest.main()
