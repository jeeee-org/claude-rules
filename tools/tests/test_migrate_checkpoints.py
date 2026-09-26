"""tools/migrate-checkpoints.py のテスト。

  python3 -m unittest discover -s tools/tests

一時ディレクトリに git リポを作り、実際に git mv まで流して確かめる。
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'migrate-checkpoints.py'

FIXTURE = {
    'docs/checkpoints/2026-01-01.md': '# 2026-01-01 作業ログ\n\n- 立ち上げ\n',
    'docs/checkpoints/2026-01-02.md': (
        '# 2026-01-02\n\n前日は[こちら](2026-01-01.md)。決定は[ADR](../adr/001.md)。\n'
        '旧方式は`docs/checkpoints/YYYY-MM-DD.md`だった。\n'
    ),
    'docs/adr/001.md': '# ADR-001\n\n経緯は[checkpoint](../checkpoints/2026-01-02.md#経緯)。\n',
    'PROGRESS.md': (
        '- [x] 完了 → [01-01](docs/checkpoints/2026-01-01.md) [01-02](docs/checkpoints/2026-01-02.md)\n'
        '参照: docs/checkpoints/2026-01-01.md\n'
    ),
    'data/refs.json': '{"see": "docs/checkpoints/2026-01-02.md"}\n',
}
NAMES = {'2026-01-01': '立ち上げ', '2026-01-02': 'ADRの整理'}


class MigrateCheckpointsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.repo = root / 'repo'
        self.repo.mkdir()
        self.names_file = root / 'names.tsv'  # リポの外に置き、作業ツリーを汚さない
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'test')
        # 既定の挙動（日本語のパスがエスケープされる）を、利用者の設定に左右されず再現する
        self.git('config', 'core.quotepath', 'true')
        for path, text in FIXTURE.items():
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'fixture')

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout

    def tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *args, '--repo', str(self.repo)],
                              capture_output=True, text=True)

    def write_names(self, names):
        self.names_file.write_text(''.join(f'{d}\t{n}\n' for d, n in names.items()), encoding='utf-8')

    def read(self, path):
        return (self.repo / path).read_text(encoding='utf-8')

    def test_plan_lists_dates_without_touching_the_tree(self):
        r = self.tool('plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('2026-01-01\t', r.stdout)
        self.assertIn('2026-01-02\t', r.stdout)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_apply_moves_retitles_and_rewrites_references(self):
        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.repo / 'docs/checkpoints').exists())

        first = self.read('checkpoints/2026-01-01-立ち上げ.md')
        second = self.read('checkpoints/2026-01-02-ADRの整理.md')
        self.assertTrue(first.startswith('# 2026-01-01 立ち上げ\n'))
        self.assertTrue(second.startswith('# 2026-01-02 ADRの整理\n'))
        self.assertIn('](2026-01-01-立ち上げ.md)', second)          # checkpoint 同士
        self.assertIn('](../docs/adr/001.md)', second)              # 1段浅くなった分の相対パス
        self.assertIn('`docs/checkpoints/YYYY-MM-DD.md`', second)   # 方式の説明は記録として残す

        self.assertIn('](../../checkpoints/2026-01-02-ADRの整理.md#経緯)', self.read('docs/adr/001.md'))
        progress = self.read('PROGRESS.md')
        self.assertIn('](checkpoints/2026-01-01-立ち上げ.md)', progress)
        self.assertIn('](checkpoints/2026-01-02-ADRの整理.md)', progress)
        self.assertIn('参照: checkpoints/2026-01-01-立ち上げ.md', progress)  # リンクでない本文
        self.assertIn('checkpoints/2026-01-02-ADRの整理.md', self.read('data/refs.json'))

        status = self.git('status', '--porcelain')
        self.assertTrue(any(line.startswith('R') for line in status.splitlines()), status)  # 履歴を保った移動
        self.assertEqual(self.tool('check').returncode, 0)

    def add(self, files):
        for path, text in files.items():
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'more')

    def test_dated_prefix_names_are_moved_by_old_file_name(self):
        # 「日付＋英語名」「日付_日本語」も、対応表の1列目に旧ファイル名を書けば移せる
        self.add({'docs/checkpoints/2026-01-03-llm-judge.md': '# 判断役の検討\n',
                  'docs/checkpoints/2026-01-04_画面の整理.md': '# 画面\n\n前は[判断役](2026-01-03-llm-judge.md)。\n',
                  'NOTES.md': '[検討](docs/checkpoints/2026-01-03-llm-judge.md)\n'})
        plan = self.tool('plan')
        self.assertIn('2026-01-03-llm-judge\tllm-judge', plan.stdout)   # 名前の候補は日付の後ろ
        self.assertIn('2026-01-04_画面の整理\t画面の整理', plan.stdout)
        self.write_names({**NAMES, '2026-01-03-llm-judge': '判断役-検討', '2026-01-04_画面の整理': '画面-整理'})
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.repo / 'checkpoints/2026-01-03-判断役-検討.md').exists())
        self.assertIn('](2026-01-03-判断役-検討.md)', self.read('checkpoints/2026-01-04-画面-整理.md'))
        self.assertIn('](checkpoints/2026-01-03-判断役-検討.md)', self.read('NOTES.md'))
        self.assertNotIn('日付名でないので残した', r.stderr)

    def test_names_that_collide_after_the_move_are_refused(self):
        self.add({'docs/checkpoints/2026-01-01-extra.md': '# x\n'})
        self.write_names({**NAMES, '2026-01-01-extra': '立ち上げ'})
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 2)
        self.assertIn('重なる', r.stderr)

    def test_links_inside_code_and_to_missing_targets_are_left_alone(self):
        self.add({'docs/checkpoints/2026-01-05.md': (
            '# 2026-01-05\n\n例: `[text](url)` と書く。\n```\n[見本](sample.md)\n```\n'
            '書き損じ[無い先](nothing/here.md)。本物は[ADR](../adr/001.md)。\n')})
        self.write_names({**NAMES, '2026-01-05': '例示'})
        r = self.tool('apply', '--names', str(self.names_file))
        text = self.read('checkpoints/2026-01-05-例示.md')
        self.assertIn('`[text](url)`', text)
        self.assertIn('[見本](sample.md)', text)
        self.assertIn('[無い先](nothing/here.md)', text)
        self.assertIn('](../docs/adr/001.md)', text)  # 実在する先は張り替える
        self.assertNotIn('`[text](url)`', r.stdout)  # 検査もコードの中を見ない

    def test_symlink_is_not_rewritten_and_is_checked_at_its_real_place(self):
        other = Path(self._tmp.name) / 'other'
        other.mkdir()
        (other / 'NOTES.md').write_text('[隣](sibling.md) と [旧](docs/checkpoints/2026-01-01.md)\n'
                                        '本文の docs/checkpoints/2026-01-01.md は隣のPJの記録\n', encoding='utf-8')
        (other / 'sibling.md').write_text('x\n', encoding='utf-8')
        (self.repo / 'NOTES-shared.md').symlink_to(other / 'NOTES.md')
        self.git('add', '-A'); self.git('commit', '-q', '-m', 'link')
        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertIn('[旧](docs/checkpoints/2026-01-01.md)', (other / 'NOTES.md').read_text(encoding='utf-8'))  # 実体を書き換えない
        self.assertNotIn('NOTES-shared.md', r.stdout)  # 実体の隣にある sibling.md へのリンクは切れていない

    def test_apply_refuses_dirty_tree(self):
        (self.repo / 'PROGRESS.md').write_text('変更\n', encoding='utf-8')
        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 2)
        self.assertIn('未コミット', r.stderr)
        self.assertTrue((self.repo / 'docs/checkpoints/2026-01-01.md').exists())

    def test_apply_rejects_incomplete_or_invalid_names(self):
        cases = [
            ({'2026-01-01': '立ち上げ'}, '対応表に無い日付'),
            ({**NAMES, '2026-01-02': 'ADR の整理'}, '使えない文字'),
            ({**NAMES, '2026-01-02': ''}, '名前が空'),
            ({**NAMES, '2026-01-03': '余分'}, '無い日付が対応表にある'),
        ]
        for names, message in cases:
            with self.subTest(message=message):
                self.write_names(names)
                r = self.tool('apply', '--names', str(self.names_file))
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn(message, r.stderr)
                self.assertEqual(self.git('status', '--porcelain'), '')

    def test_apply_refuses_when_nothing_is_left(self):
        self.write_names(NAMES)
        self.assertEqual(self.tool('apply', '--names', str(self.names_file)).returncode, 0)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'migrated')
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 2)
        self.assertIn('checkpointが無い', r.stderr)

    def test_check_reports_leftover_path_and_dead_link(self):
        with open(self.repo / 'PROGRESS.md', 'a', encoding='utf-8') as f:
            f.write('[消えた](checkpoints/2026-09-09-無い.md)\n')
        r = self.tool('check')
        self.assertEqual(r.returncode, 1)
        self.assertIn('旧パスが残っている', r.stdout)
        self.assertIn('リンクが切れている', r.stdout)

    def test_check_ignores_old_paths_recorded_inside_checkpoints(self):
        self.write_names(NAMES)
        self.assertEqual(self.tool('apply', '--names', str(self.names_file)).returncode, 0)
        (self.repo / 'checkpoints/2026-01-03-記録置き場の移行.md').write_text(
            '| `docs/checkpoints/2026-01-01.md` | `checkpoints/2026-01-01-立ち上げ.md` |\n', encoding='utf-8')
        self.git('add', '-A')
        r = self.tool('check')
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_apply_rewrites_directory_link_and_check_lists_other_mentions(self):
        # meeting-scribe の移行で、README の表のディレクトリリンクと .gitignore のコメントが残った
        (self.repo / 'README.md').write_text(
            '| [docs/checkpoints/](docs/checkpoints/) | 日ごとの詳細ログ |\n', encoding='utf-8')
        (self.repo / '.gitignore').write_text('# 中身は読んで docs/checkpoints/ へ畳む\nprivate/\n', encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'dir refs')
        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # 言及は確かめるだけで、失敗にはしない
        self.assertIn('](checkpoints/)', self.read('README.md'))
        self.assertIn('確かめる', r.stdout)
        self.assertIn('.gitignore:1:', r.stdout)
        self.assertIn('README.md:1:', r.stdout)  # リンクの文字列（表示側）は人が直す
        self.assertNotIn('checkpoints/2026-01-02-ADRの整理.md:', r.stdout)  # checkpoint 内の記録は出さない

    def test_apply_reanchors_links_that_point_outside_the_checkpoint_dir(self):
        # 移動で階層が1段浅くなるぶん、checkpoint から外を指す相対リンクの行き先がずれる
        (self.repo / 'docs/資料').mkdir(parents=True)
        (self.repo / 'docs/資料/一覧.md').write_text('# 一覧\n', encoding='utf-8')
        with open(self.repo / 'docs/checkpoints/2026-01-01.md', 'a', encoding='utf-8') as f:
            f.write('一覧は[資料一覧](../資料/一覧.md)、進捗は[PROGRESS](../../PROGRESS.md)。\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'outward links')
        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        moved = self.read('checkpoints/2026-01-01-立ち上げ.md')
        self.assertIn('](../docs/資料/一覧.md)', moved)
        self.assertIn('](../PROGRESS.md)', moved)

    def test_rename_only_entry_when_the_move_was_already_done(self):
        # 一括移行で置き場だけ揃え、名前が YYYY-MM-DD.md のまま残ったPJ。参照は移動の時に直してある
        self.git('mv', 'docs/checkpoints', 'checkpoints')
        (self.repo / 'PROGRESS.md').write_text(
            '- [x] 完了 → [01-01](checkpoints/2026-01-01.md)\n参照: checkpoints/2026-01-01.md\n', encoding='utf-8')
        (self.repo / 'docs/adr/001.md').write_text(
            '# ADR-001\n\n経緯は[checkpoint](../../checkpoints/2026-01-02.md#経緯)。\n', encoding='utf-8')
        (self.repo / 'data/refs.json').write_text('{"see": "checkpoints/2026-01-02.md"}\n', encoding='utf-8')
        (self.repo / 'checkpoints/2026-01-02.md').write_text(
            '# 2026-01-02\n\n前日は[こちら](2026-01-01.md)。決定は[ADR](../docs/adr/001.md)。\n', encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'hand move')

        r = self.tool('plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('改名だけ', r.stderr)
        self.assertIn('2026-01-01\t', r.stdout)

        self.write_names(NAMES)
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.read('checkpoints/2026-01-01-立ち上げ.md').startswith('# 2026-01-01 立ち上げ\n'))
        second = self.read('checkpoints/2026-01-02-ADRの整理.md')
        self.assertIn('](2026-01-01-立ち上げ.md)', second)
        self.assertIn('](../docs/adr/001.md)', second)   # 階層は動かないので外向きはそのまま
        self.assertIn('](../../checkpoints/2026-01-02-ADRの整理.md#経緯)', self.read('docs/adr/001.md'))
        progress = self.read('PROGRESS.md')
        self.assertIn('](checkpoints/2026-01-01-立ち上げ.md)', progress)
        self.assertIn('参照: checkpoints/2026-01-01-立ち上げ.md', progress)   # リンクでない本文
        self.assertIn('checkpoints/2026-01-02-ADRの整理.md', self.read('data/refs.json'))
        self.assertTrue(any(line.startswith('R') for line in self.git('status', '--porcelain').splitlines()))

    def test_check_catches_the_outward_link_a_hand_move_broke(self):
        # 手で checkpoints/ へ上げると外向きの相対パスが1段ずれる。apply を通していないので誰も直していない
        self.git('mv', 'docs/checkpoints', 'checkpoints')
        with open(self.repo / 'checkpoints/2026-01-02.md', 'a', encoding='utf-8') as f:
            f.write('別リポは[外](../../他所/x.md)。\n')
        self.git('commit', '-q', '-am', 'hand move')
        r = self.tool('check')
        self.assertEqual(r.returncode, 1)
        self.assertIn('リンクが切れている: ../adr/001.md', r.stdout)   # 旧い位置なら docs/adr/001.md だった
        self.assertNotIn('他所', r.stdout)   # リポの外へ出る行き先は判断しない

    def test_check_reports_a_reference_left_at_the_old_name(self):
        self.write_names(NAMES)
        self.assertEqual(self.tool('apply', '--names', str(self.names_file)).returncode, 0)
        (self.repo / 'NOTES.md').write_text('本文: checkpoints/2026-01-01.md\n', encoding='utf-8')
        self.git('add', '-A')
        r = self.tool('check')
        self.assertEqual(r.returncode, 1)
        self.assertIn('改名前の名前のまま残っている', r.stdout)


MONOREPO = {
    # 本体と tasks/x が同じ日付の checkpoint を持つ（モノレポで24ファイルが別の文書を指した事故の再現）
    'docs/checkpoints/2026-07-13.md': '# 2026-07-13\n\n- 本体の作業\n',
    'PROGRESS.md': '- [本体](docs/checkpoints/2026-07-13.md)\n参照: docs/checkpoints/2026-07-13.md\n',
    'README.md': (
        'タスクの記録は tasks/x/docs/checkpoints/2026-07-13.md を見る。'
        '本体は docs/checkpoints/2026-07-13.md。\n'
        '| [docs/checkpoints/](docs/checkpoints/) | 本体の記録 |\n'
    ),
    'tasks/x/docs/checkpoints/2026-07-13.md': '# 2026-07-13\n\n- タスクの作業\n',
    'tasks/x/NOTES.md': (
        '- [自分の記録](docs/checkpoints/2026-07-13.md)\n'
        '本文: docs/checkpoints/2026-07-13.md\n'
        '置き場: docs/checkpoints/\n'
    ),
    'tasks/x/sub/deep.md': '上の記録は [ここ](../docs/checkpoints/2026-07-13.md)。本文でも docs/checkpoints/2026-07-13.md。\n',
}


class MonorepoTest(MigrateCheckpointsTest):
    """1つの git リポに PJ が複数ある形。--repo にサブディレクトリを渡して、そのPJだけを移す"""

    def setUp(self):
        super().setUp()
        for path in FIXTURE:
            (self.repo / path).unlink()
        for path, text in MONOREPO.items():
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'monorepo')

    def tool_at(self, base, *args):
        return subprocess.run([sys.executable, str(TOOL), *args, '--repo', str(self.repo / base)],
                              capture_output=True, text=True)

    # 親クラスのテストは FIXTURE 前提なので走らせない
    def run(self, result=None):
        if self._testMethodName.startswith('test_') and not self._testMethodName.startswith('test_mono_'):
            return
        return super().run(result)

    def test_mono_root_migration_leaves_other_projects_alone(self):
        self.write_names({'2026-07-13': '本体'})
        r = self.tool('apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read('tasks/x/NOTES.md'), MONOREPO['tasks/x/NOTES.md'])   # 同じ日付でも別の文書
        self.assertEqual(self.read('tasks/x/sub/deep.md'), MONOREPO['tasks/x/sub/deep.md'])
        self.assertTrue((self.repo / 'tasks/x/docs/checkpoints/2026-07-13.md').exists())
        readme = self.read('README.md')
        self.assertIn('tasks/x/docs/checkpoints/2026-07-13.md を見る', readme)   # 場所付きの言及は別PJのもの
        self.assertIn('本体は checkpoints/2026-07-13-本体.md。', readme)
        self.assertIn('](checkpoints/)', readme)
        self.assertIn('参照: checkpoints/2026-07-13-本体.md', self.read('PROGRESS.md'))
        self.assertNotIn('tasks/x', r.stdout)   # 他PJの docs/checkpoints/ を「旧パス」「確かめる」に出さない

    def test_mono_subdir_migration_respects_repo_and_stays_in_tree(self):
        self.write_names({'2026-07-13': 'タスク'})
        r = self.tool_at('tasks/x', 'plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('2026-07-13\t'), 1)
        r = self.tool_at('tasks/x', 'apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.repo / 'tasks/x/checkpoints/2026-07-13-タスク.md').exists())
        self.assertFalse((self.repo / 'tasks/x/docs/checkpoints').exists())
        # 本体は触らない
        self.assertTrue((self.repo / 'docs/checkpoints/2026-07-13.md').exists())
        self.assertEqual(self.read('PROGRESS.md'), MONOREPO['PROGRESS.md'])
        # タスク内の参照はリンクも本文も張り直す（深い階層からも）
        notes = self.read('tasks/x/NOTES.md')
        self.assertIn('](checkpoints/2026-07-13-タスク.md)', notes)
        self.assertIn('本文: checkpoints/2026-07-13-タスク.md', notes)
        deep = self.read('tasks/x/sub/deep.md')
        self.assertIn('](../checkpoints/2026-07-13-タスク.md)', deep)
        self.assertIn('本文でも checkpoints/2026-07-13-タスク.md', deep)
        # 本体側から場所付きで引いていた分は、その場所として張り直す。本体自身の言及はそのまま
        readme = self.read('README.md')
        self.assertIn('tasks/x/checkpoints/2026-07-13-タスク.md を見る', readme)
        self.assertIn('本体は docs/checkpoints/2026-07-13.md。', readme)
        # check はタスクの木の外（本体の docs/checkpoints/）を報告しない
        c = self.tool_at('tasks/x', 'check')
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertNotIn('README.md', c.stdout)
        self.assertNotIn('PROGRESS.md', c.stdout)
        self.assertIn('tasks/x/NOTES.md:3:', c.stdout)   # タスク自身の置き場の言及は「確かめる」に出す

    def test_mono_apply_lists_the_files_it_rewrote_outside_the_project(self):
        """PJの外の参照も張り替わる。ステージし損ねないよう一覧で出す"""
        self.write_names({'2026-07-13': 'タスク'})
        r = self.tool_at('tasks/x', 'apply', '--names', str(self.names_file))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PJの外の1ファイルも張り替えた', r.stderr)
        self.assertIn('   README.md', r.stderr)
        self.assertIn('README.md（PJの外）', r.stdout)
        self.assertNotIn('tasks/x/NOTES.md（PJの外）', r.stdout)

    def test_mono_repo_outside_git_is_refused(self):
        r = subprocess.run([sys.executable, str(TOOL), 'plan', '--repo', str(self.repo / 'no-such-dir')],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn('ディレクトリが無い', r.stderr)


if __name__ == '__main__':
    unittest.main()
