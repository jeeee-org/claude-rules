#!/usr/bin/env python3
"""共通ルールの正本（rules/common-rules.md）から、読み手ごとの版を作る。

    python3 tools/build-rules.py            # rules/global-rules.md と rules/codex-global-rules.md を書き直す
    python3 tools/build-rules.py --check    # 生成物が正本と揃っているかだけ見る（揃っていなければ exit 1）
    python3 tools/build-rules.py --variant embed-both   # 1つの版の本文を標準出力へ

版は5つ。読み手（claude / codex）と置き場（global / embed）の組み合わせ:
  claude-global  ~/.claude/CLAUDE.md へ install.sh が注入する
  codex-global   ~/.codex/AGENTS.md へ install.sh が注入する
  embed-claude   PJの CLAUDE.md へ tools/embed-rules.py が書き込む（Claudeだけの相手）
  embed-codex    PJの AGENTS.md へ書き込む（Codexだけの相手）
  embed-both     PJの AGENTS.md へ書き込み、CLAUDE.md から @AGENTS.md で読ませる

正本の書き方:
  {{名前}}                                  版ごとの語（VARIANTS の vars）に置き換わる
  <!-- if:条件 -->…<!-- endif -->            条件が立つ版にだけ残る。行の途中にも置ける（入れ子は不可）
  条件は印（claude / codex / global / embed）で書く。`,` = または、`+` = かつ、`!` = でない
  例 if:claude+global（Claudeのグローバルだけ）、if:!embed、if:claude,codex
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'rules' / 'common-rules.md'

_CLAUDE_SKILL = '`.claude/skills/<name>/SKILL.md`'
_CODEX_SKILL = '`.agents/skills/<name>/SKILL.md`'
_EMBED_CHECK = '`.claude-rules/check-limits.sh`'

VARIANTS = {
    'claude-global': {
        'flags': {'claude', 'global'},
        'vars': {'PJ': 'CLAUDE.md', 'LIMIT_COMMON': 'グローバルCLAUDE.md', 'LIMIT_PJ': 'PJ CLAUDE.md',
                 'CHECK_LIMITS': '~/.claude/tools/check-limits.sh', 'START_SCOPE': 'グローバル＋PJ',
                 'SKILL_PATH': _CLAUDE_SKILL, 'INIT': '/init-rules'},
    },
    'codex-global': {
        'flags': {'codex', 'global'},
        'vars': {'PJ': 'AGENTS.md', 'LIMIT_COMMON': 'グローバルAGENTS.md', 'LIMIT_PJ': 'PJ AGENTS.md',
                 'CHECK_LIMITS': '~/.codex/tools/check-limits.sh', 'START_SCOPE': 'グローバル＋PJ',
                 'SKILL_PATH': _CODEX_SKILL, 'INIT': '$init-rules'},
    },
    'embed-claude': {
        'flags': {'claude', 'embed'},
        'vars': {'PJ': 'CLAUDE.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ CLAUDE.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CLAUDE_SKILL},
    },
    'embed-codex': {
        'flags': {'codex', 'embed'},
        'vars': {'PJ': 'AGENTS.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ AGENTS.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CODEX_SKILL},
    },
    'embed-both': {
        'flags': {'claude', 'codex', 'embed'},
        'vars': {'PJ': 'AGENTS.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ AGENTS.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CLAUDE_SKILL + '（Codexは`.agents/skills/`）'},
    },
}

# install.sh が注入に使う生成物。マーカー名は既存の ~/.claude/CLAUDE.md・~/.codex/AGENTS.md と揃える
GLOBAL_OUTPUTS = {
    'claude-global': (ROOT / 'rules' / 'global-rules.md', 'claude-rules'),
    'codex-global': (ROOT / 'rules' / 'codex-global-rules.md', 'codex-rules'),
}

_BLOCK = re.compile(r'^<!-- if:(\S+) -->\n(.*?)^<!-- endif -->\n', re.M | re.S)
_INLINE = re.compile(r'<!-- if:(\S+) -->(.*?)<!-- endif -->', re.S)
_VAR = re.compile(r'\{\{(\w+)\}\}')


def holds(cond: str, flags: set[str]) -> bool:
    def atom(a: str) -> bool:
        return (a[1:] not in flags) if a.startswith('!') else (a in flags)
    return any(all(atom(a) for a in term.split('+')) for term in cond.split(','))


def render(variant: str, source: str | None = None) -> str:
    """版の本文（マーカー行を除く）を返す。"""
    spec = VARIANTS[variant]
    text = SOURCE.read_text(encoding='utf-8') if source is None else source
    keep = lambda m: m.group(2) if holds(m.group(1), spec['flags']) else ''
    text = _BLOCK.sub(keep, text)
    text = _INLINE.sub(keep, text)

    def var(m):
        name = m.group(1)
        if name not in spec['vars']:
            raise KeyError(f'{variant}: {{{{{name}}}}} の値が無い')
        return spec['vars'][name]
    text = _VAR.sub(var, text)
    if '<!-- if:' in text or '<!-- endif' in text:
        raise ValueError(f'{variant}: 閉じていない条件ブロックがある')
    text = re.sub(r'\n{3,}', '\n\n', text).strip('\n')
    return text + '\n'


def global_file(variant: str) -> str:
    path, marker = GLOBAL_OUTPUTS[variant]
    head = (f'<!-- {marker}:begin (claude-rules/install.shが管理。手動編集しない'
            ' — 変更はリポのrules/common-rules.mdへ) -->\n')
    return head + render(variant) + f'\n<!-- {marker}:end -->\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='生成物が正本と揃っているかだけ見る')
    ap.add_argument('--variant', choices=sorted(VARIANTS), help='1つの版の本文を標準出力へ')
    args = ap.parse_args(argv)

    if args.variant:
        sys.stdout.write(render(args.variant))
        return 0
    stale = []
    for variant, (path, _) in GLOBAL_OUTPUTS.items():
        want = global_file(variant)
        have = path.read_text(encoding='utf-8') if path.exists() else None
        if have == want:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.write_text(want, encoding='utf-8')
    if args.check:
        for p in stale:
            print(f'✗ {p} が正本（rules/common-rules.md）と揃っていません。tools/build-rules.py を実行してください', file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        print(f'  - {p} を正本から作り直しました（commitに含めてください）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
