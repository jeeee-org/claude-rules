#!/usr/bin/env python3
"""共通ルールを、グローバルでなく対象PJのルールファイルへ書き込む（グローバルを入れない相手へ配る時）。

    python3 <claude-rules>/tools/embed-rules.py --list-options      # 選べる個人の運用の一覧
    python3 <claude-rules>/tools/embed-rules.py <PJ> --options autopush,worktree [--target both|claude|codex] [--dry-run]
    python3 <claude-rules>/tools/embed-rules.py <PJ>             # 2回目以降: 前回の選択と書き込み先のまま最新へ
    python3 <claude-rules>/tools/embed-rules.py <PJ> --check     # 書き込み済みの版が最新か（古ければ exit 1）
    python3 <claude-rules>/tools/embed-rules.py <PJ> --remove    # 書き込んだものを取り除く

導入はAIが案内する前提（スキル install-rules）。オプションを覚えておく必要は無い。

--options で個人の運用をPJごとに選ぶ（カンマ区切り。none = 1つも入れない、all = 全部）。
初回は必須（黙って既定を入れない）。選んだものはマーカー行に残り、2回目以降は省略すると引き継ぐ。
コミットの書き方・memory不使用・AI署名なし・外に出す文面・応答の書き方は選択ではなく常に入る。

--target（初回の既定 both、2回目以降は前回の先）で書き込む先が変わる:
  both    AGENTS.md の先頭へ共通ルールを書く（PJのルールは AGENTS.md に統一。Claude Codeは
          v2.1.277以降 AGENTS.md を直接読む）。ただし PJ に CLAUDE.md が既にある時だけ、その先頭に
          @AGENTS.md を置く（CLAUDE.mdがあるとClaude CodeはAGENTS.mdを読まないため）。無ければ作らない
  claude  CLAUDE.md の先頭へ書く（Claudeだけの相手）
  codex   AGENTS.md の先頭へ書く（Codexだけの相手）

- 共通ルールはマーカー（claude-rules:embed:begin / end）で囲む。2回目以降はマーカー間だけを差し替え、
  外に書かれたPJ固有の指示には触らない。マーカー行に版（正本のcommit）と種類と選んだ運用を刻む
- 上限の判定に使う check-limits.sh を <PJ>/.claude-rules/ へ置く（本文がこの場所を指す）
- このPCにグローバルの共通ルールも入っていれば、二重に読まれることを知らせる（止めはしない）
- commitはしない
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('build_rules', ROOT / 'tools' / 'build-rules.py')
build_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_rules)

BEGIN = 'claude-rules:embed:begin'
END = 'claude-rules:embed:end'
IMPORT_MARK = 'claude-rules:embed:import'
IMPORT_LINES = (f'<!-- {IMPORT_MARK} (claude-rules/tools/embed-rules.pyが書き込む。'
                '共通ルールとPJ固有の指示はAGENTS.mdにある) -->\n@AGENTS.md\n')
UPSTREAM = 'https://github.com/jeeee-org/claude-rules'
TOOL_DIR = '.claude-rules'

_BLOCK_RE = re.compile(rf'^<!-- {re.escape(BEGIN)}.*?^<!-- {re.escape(END)} -->\n?', re.M | re.S)
_IMPORT_RE = re.compile(rf'^<!-- {re.escape(IMPORT_MARK)}.*?-->\n@AGENTS\.md\n?', re.M)
_VERSION_RE = re.compile(rf'(<!-- {re.escape(BEGIN)} \(版 )\S+ /')
_HEAD_RE = re.compile(rf'<!-- {re.escape(BEGIN)} \(版 \S+ / embed-(\w+) / 選択 ([^。]+)。')


def source_version() -> str:
    """正本のcommit。未commitの変更があれば +dirty を付ける。gitが無ければ unknown。"""
    try:
        sha = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%h', '--', 'rules/common-rules.md'],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'rules/common-rules.md'],
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'
    return (sha or 'uncommitted') + ('+dirty' if dirty else '')


def block_text(variant: str, version: str, options: set[str]) -> str:
    chosen = ','.join(o for o in build_rules.OPTIONS if o in options) or 'なし'
    head = (f'<!-- {BEGIN} (版 {version} / {variant} / 選択 {chosen}。claude-rules/tools/embed-rules.pyが書き込む。'
            f'中を編集しない — 出典 {UPSTREAM} のrules/common-rules.md) -->\n')
    return head + build_rules.render(variant, options=options) + f'\n<!-- {END} -->\n'


def stored(pj: Path) -> tuple[str, set[str]] | None:
    """前回書き込んだ時の（書き込み先, 選んだ運用）。無ければ None。"""
    for name in ('AGENTS.md', 'CLAUDE.md'):
        f = pj / name
        if f.exists():
            m = _HEAD_RE.search(f.read_text(encoding='utf-8'))
            if m:
                return m.group(1), (set() if m.group(2) == 'なし' else set(m.group(2).split(',')))
    return None


def parse_options(text: str) -> set[str]:
    if text == 'none':
        return set()
    if text == 'all':
        return set(build_rules.OPTIONS)
    chosen = {t.strip() for t in text.split(',') if t.strip()}
    unknown = chosen - set(build_rules.OPTIONS)
    if unknown:
        raise ValueError(f'知らない個人の運用: {", ".join(sorted(unknown))}（--list-options で一覧）')
    return chosen


def list_options() -> str:
    lines = ['選べる個人の運用（--options にカンマ区切りで渡す。none / all も可）:']
    for name, (what, note) in build_rules.OPTIONS.items():
        lines.append(f'  {name:<11} {what}（{note}）')
    lines.append('常に入るもの: コミットの書き方・memory不使用・AI署名なし・外に出す文面でMarkdownを使わない・応答の書き方')
    return '\n'.join(lines) + '\n'


def put_block(text: str, block: str) -> str:
    """マーカー間を差し替える。無ければ先頭へ置く（PJ固有の指示はその下に続く）。"""
    if _BLOCK_RE.search(text):
        return _BLOCK_RE.sub(lambda _: block, text, count=1)
    return block + ('\n' + text if text.strip() else '')


def drop_block(text: str) -> str:
    return _BLOCK_RE.sub('', text, count=1).lstrip('\n')


def put_import(text: str) -> str:
    if re.search(r'^@AGENTS\.md\s*$', text, re.M):
        return text
    return IMPORT_LINES + ('\n' + text if text.strip() else '')


def drop_import(text: str) -> str:
    return _IMPORT_RE.sub('', text, count=1).lstrip('\n')


def plan(pj: Path, target: str, version: str, options: set[str]) -> dict[Path, str | None]:
    """書き込み後の中身を {パス: 中身} で返す（None は削除）。"""
    variant = f'embed-{target}'
    rules_file = pj / ('CLAUDE.md' if target == 'claude' else 'AGENTS.md')
    out: dict[Path, str | None] = {}
    cur = rules_file.read_text(encoding='utf-8') if rules_file.exists() else ''
    out[rules_file] = put_block(cur, block_text(variant, version, options))
    cm = pj / 'CLAUDE.md'
    if target == 'both' and cm.exists():
        out[cm] = put_import(cm.read_text(encoding='utf-8'))
    return out


def plan_remove(pj: Path) -> dict[Path, str | None]:
    out: dict[Path, str | None] = {}
    for name in ('AGENTS.md', 'CLAUDE.md'):
        f = pj / name
        if not f.exists():
            continue
        cur = f.read_text(encoding='utf-8')
        new = drop_import(drop_block(cur))
        if new != cur:
            out[f] = new if new.strip() else None
    return out


def warnings(pj: Path, target: str) -> list[str]:
    msgs = []
    cc = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')) / 'CLAUDE.md'
    cx = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'AGENTS.md'
    if target in ('both', 'claude') and cc.exists() and 'claude-rules:begin' in cc.read_text(encoding='utf-8'):
        msgs.append(f'このPCの{cc}にも共通ルールがあります。このPJをこのPCのClaudeで開くと二重に読まれます')
    if target in ('both', 'codex') and cx.exists() and 'codex-rules:begin' in cx.read_text(encoding='utf-8'):
        msgs.append(f'このPCの{cx}にも共通ルールがあります。このPJをこのPCのCodexで開くと二重に読まれます')
    cm, am = pj / 'CLAUDE.md', pj / 'AGENTS.md'
    if target == 'both' and cm.exists():
        rest = drop_import(drop_block(cm.read_text(encoding='utf-8'))).strip()
        if rest:
            msgs.append('CLAUDE.mdにPJ固有の指示があります。Codexからは読まれません。'
                        '両方に効かせるならAGENTS.md（共通ルールのブロックの下）へ移してください')
        if _BLOCK_RE.search(cm.read_text(encoding='utf-8')):
            msgs.append('CLAUDE.mdに以前の共通ルールのブロック（--target claude）が残っています。'
                        'AGENTS.mdと二重に読まれるので、CLAUDE.mdのマーカー間を消してください')
    if target == 'claude' and am.exists() and _BLOCK_RE.search(am.read_text(encoding='utf-8')):
        msgs.append('AGENTS.mdに以前の共通ルールのブロックが残っています（Codexは引き続きそれを読みます）')
    return msgs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pj', type=Path, nargs='?', help='書き込む先のPJのルート')
    ap.add_argument('--target', choices=['both', 'claude', 'codex'], help='初回の既定 both、以後は前回の先')
    ap.add_argument('--options', help='個人の運用（カンマ区切り / none / all）。初回は必須')
    ap.add_argument('--list-options', action='store_true', help='選べる個人の運用の一覧')
    ap.add_argument('--dry-run', action='store_true', help='書き換えずに、変わるファイルだけ出す')
    ap.add_argument('--check', action='store_true', help='書き込み済みの版が最新か見る（古ければ exit 1）')
    ap.add_argument('--remove', action='store_true', help='書き込んだブロックと読み込みの行・.claude-rules/を取り除く')
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(line_buffering=True)  # 警告（stderr）と並びを揃える
    if args.list_options:
        sys.stdout.write(list_options())
        return 0
    if args.pj is None:
        ap.error('PJのルートを指定してください')
    pj = args.pj.resolve()
    if not pj.is_dir():
        print(f'✗ {pj} がディレクトリではありません', file=sys.stderr)
        return 2

    tool_src = ROOT / 'tools' / 'check-limits.sh'
    tool_dst = pj / TOOL_DIR / 'check-limits.sh'
    if args.remove:
        changes = plan_remove(pj)
    else:
        prev = stored(pj)
        target = args.target or (prev[0] if prev else 'both')
        if args.options is not None:
            try:
                options = parse_options(args.options)
            except ValueError as e:
                print(f'✗ {e}', file=sys.stderr)
                return 2
        elif prev:
            options = prev[1]
        else:
            print('✗ 初回は --options で個人の運用を選んでください（黙って既定を入れない）。\n',
                  file=sys.stderr)
            sys.stderr.write(list_options())
            return 2
        args.target = target
        changes = plan(pj, target, source_version(), options)

    diff = []
    for f, new in changes.items():
        cur = f.read_text(encoding='utf-8') if f.exists() else None
        if cur != new:
            diff.append((f, new))
    tool_stale = (not args.remove) and (not tool_dst.exists() or tool_dst.read_bytes() != tool_src.read_bytes())

    if args.check:
        # 版の刻みだけが違う場合（正本に変化が無い）は最新とみなす
        stale = []
        for f, new in diff:
            cur = f.read_text(encoding='utf-8') if f.exists() else ''
            if new is None or _VERSION_RE.sub(r'\1', cur) != _VERSION_RE.sub(r'\1', new):
                stale.append(f)
        for f in stale:
            print(f'✗ {f.relative_to(pj)} の共通ルールが最新ではありません', file=sys.stderr)
        if tool_stale:
            print(f'✗ {TOOL_DIR}/check-limits.sh が最新ではありません', file=sys.stderr)
        return 1 if stale or tool_stale else 0

    verb = '変わる' if args.dry_run else '書き換えた'
    for f, new in diff:
        rel = f.relative_to(pj)
        if not args.dry_run:
            if new is None:
                f.unlink()
            else:
                f.write_text(new, encoding='utf-8')
        print(f'  - {rel}（{"削除" if new is None else verb}）')
    tool_gone = args.remove and (pj / TOOL_DIR).exists()
    if tool_gone:
        if not args.dry_run:
            shutil.rmtree(pj / TOOL_DIR)
        print(f'  - {TOOL_DIR}/（削除）')
    elif tool_stale:
        if not args.dry_run:
            tool_dst.parent.mkdir(exist_ok=True)
            shutil.copy2(tool_src, tool_dst)
            tool_dst.chmod(0o755)
        print(f'  - {TOOL_DIR}/check-limits.sh（{verb}）')
    if not diff and not tool_stale and not tool_gone:
        print('  変更なし')

    if not args.remove:
        for m in warnings(pj, args.target):
            print(f'※ {m}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
