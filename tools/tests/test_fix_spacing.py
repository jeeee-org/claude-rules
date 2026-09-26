"""tools/fix-spacing.pyのテスト。

  python3 -m unittest discover -s tools/tests

一時ディレクトリにファイルを作り、コマンドとして実行して確かめる。
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'fix-spacing.py'


class FixSpacingTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_tool(self, text, *args):
        path = self.root / 'doc.md'
        path.write_text(text, encoding='utf-8')
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(path), *args],
            capture_output=True, text=True)
        return proc, path.read_text(encoding='utf-8')

    def fixed(self, text, *args):
        _, out = self.run_tool(text, '--write', *args)
        return out

    # --- 落とす ---

    def test_英数字と日本語の境目を詰める(self):
        self.assertEqual(
            self.fixed('Windows 側で VAD を回す。\n'),
            'Windows側でVADを回す。\n')

    def test_印を両側とも透かす(self):
        self.assertEqual(
            self.fixed('**Haiku 4.5 で十分**。`install.sh` を実行する。\n'),
            '**Haiku 4.5で十分**。`install.sh`を実行する。\n')

    def test_閉じ括弧と全角の読点の境目も詰める(self):
        self.assertEqual(
            self.fixed('録音（16kHz mono） と挿入、 STT の順。\n'),
            '録音（16kHz mono）と挿入、STTの順。\n')

    # --- 触らない ---

    def test_見出しは直さず判断が要る候補に回す(self):
        proc, out = self.run_tool('## WSL2 DNS 断続障害\nWindows 側で動かす。\n', '--write')
        self.assertIn('## WSL2 DNS 断続障害', out)
        self.assertIn('Windows側で動かす。', out)
        self.assertIn('判断が要る（見出し', proc.stdout)

    def test_名前で引く参照の中身は触らない(self):
        text = 'NOTES.md「dev SKIP 判定基準」と`NOTES.md`「WSL2 DNS 断続障害」を見る。[[WSL2 DNS 断続障害]] も Windows 側。\n'
        out = self.fixed(text)
        self.assertIn('NOTES.md「dev SKIP 判定基準」', out)
        self.assertIn('`NOTES.md`「WSL2 DNS 断続障害」', out)
        self.assertIn('[[WSL2 DNS 断続障害]]', out)
        self.assertIn('Windows側', out)  # 参照の外は直す

    def test_共通ルールのブロックの中は触らない(self):
        text = ('<!-- claude-rules:embed:begin (版 ccc4ef9 / embed-both / 選択 autocommit。…) -->\n'
                '- 悪い例「`install.sh` を実行」\n'
                '```markdown\n'
                '### <作業名>\n'
                '<!-- claude-rules:embed:end -->\n'.replace('### <作業名>\n', '### <作業名>\n```\n')
                + '\n# AGENTS.md\nWindows 側で動かす。\n')
        out = self.fixed(text)
        self.assertIn('(版 ccc4ef9 / embed-both / 選択 autocommit。', out)
        self.assertIn('「`install.sh` を実行」', out)
        self.assertIn('Windows側で動かす。', out)  # ブロックの外は直す

    def test_インラインコードの中身は変えない(self):
        text = '見出し `## 9. 応答の書き方` を引用する。\n'
        self.assertEqual(self.fixed(text), '見出し`## 9. 応答の書き方`を引用する。\n')

    def test_行頭のマーカーの直後は残す(self):
        text = ('# 見出し\n'
                '- 箇条書き\n'
                '1. 番号\n'
                '> 引用\n'
                '- [x] チェック済み\n')
        self.assertEqual(self.fixed(text), text)

    def test_行頭の日付と章番号の直後は残す(self):
        text = ('- 2026-09-12 全体圧縮のやり方。\n'
                '- [x] 2026-09-18 記録の関門。\n'
                '### 5.2 コミットメッセージ規約\n'
                '## 9. 応答の書き方\n')
        self.assertEqual(self.fixed(text), text)

    def test_記号を挟んだ両側は残す(self):
        text = ('4軸 + checkpointの骨格。\n'
                'やること / バックログへ移す。\n'
                '話し終わり → 画面に文字。\n')
        self.assertEqual(self.fixed(text), text)

    def test_コードフェンスの中は触らない(self):
        text = ('文の VAD を詰める。\n'
                '```\n'
                'STT 754ms / 挿入 155ms\n'
                '```\n')
        self.assertEqual(
            self.fixed(text),
            '文のVADを詰める。\n```\nSTT 754ms / 挿入 155ms\n```\n')

    def test_閉じていないコードフェンスは中止する(self):
        proc, out = self.run_tool('```\nSTT 754ms\n', '--write')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('閉じていません', proc.stderr)

    def test_keepにあてはまる行は触らない(self):
        text = '悪い例「`install.sh` を実行」、良い例「`install.sh`を実行」。\n'
        self.assertEqual(self.fixed(text, '--keep', '悪い例'), text)

    # --- 判断が要る候補 ---

    def test_日本語のうしろの開き括弧は直さず出す(self):
        proc, out = self.run_tool('## 次の一手 (Top 3)\n', '--write')
        self.assertEqual(out, '## 次の一手 (Top 3)\n')
        self.assertIn('判断が要る', proc.stdout)
        self.assertIn('判断が要る候補 1行', proc.stdout)

    def test_コード印が並ぶ行は直さず出す(self):
        # 記法そのものを列挙している行。空白は項目の区切りなので詰めると読めなくなる
        text = '- 使わない：`**太字**` `*斜体*` `` `コード` `` `#`見出し `- `箇条書き\n'
        proc, out = self.run_tool(text, '--write')
        self.assertEqual(out, text)
        self.assertIn('コード印が並ぶ行', proc.stdout)

    def test_コード印が並ぶ行でもコードに接しない境目は直す(self):
        text = '- `a`と`b`と`c`と`d`を挙げる。**リポ直下（1日1件）** へ移す。\n'
        self.assertEqual(
            self.fixed(text),
            '- `a`と`b`と`c`と`d`を挙げる。**リポ直下（1日1件）**へ移す。\n')

    def test_コード印が3つまでの行は直す(self):
        self.assertEqual(
            self.fixed('`--repo`で`plan`を回し、`apply` を打つ。\n'),
            '`--repo`で`plan`を回し、`apply`を打つ。\n')

    def test_印を透かした先が閉じ括弧でも詰める(self):
        # 左が「**」で終わる行。印を片側しか透かさないと取りこぼす
        self.assertEqual(
            self.fixed('**リポ直下の`checkpoints/`（1日1件）** へ移す。\n'),
            '**リポ直下の`checkpoints/`（1日1件）**へ移す。\n')

    # --- 入口の振る舞い ---

    def test_既定では書かずに候補を出す(self):
        proc, out = self.run_tool('Windows 側。\n')
        self.assertEqual(out, 'Windows 側。\n')
        self.assertEqual(proc.returncode, 1)
        self.assertIn('直す候補 1行', proc.stdout)
        self.assertIn('+ Windows側。', proc.stdout)

    def test_直す候補が無ければ0で終わる(self):
        proc, out = self.run_tool('Windows側で回す。\n')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('直す候補 0行', proc.stdout)

    def test_writeは直して0で終わる(self):
        proc, out = self.run_tool('Windows 側。\n', '--write')
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(out, 'Windows側。\n')
        self.assertIn('直した 1行', proc.stdout)

    def test_日本語同士の空白は対象外(self):
        # §9は英数字と日本語の境目の話。日本語同士の空白は手で見る
        text = '記録ルールは グローバルに従う。\n'
        self.assertEqual(self.fixed(text), text)

    def test_読めないファイルは2で中止する(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(self.root / 'ない.md')],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_二度かけても結果が変わらない(self):
        once = self.fixed('Windows 側で VAD を回す。\n')
        path = self.root / 'doc.md'
        subprocess.run([sys.executable, str(TOOL), str(path), '--write'],
                       capture_output=True, text=True)
        self.assertEqual(path.read_text(encoding='utf-8'), once)


if __name__ == '__main__':
    unittest.main()
