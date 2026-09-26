#!/usr/bin/env python3
"""共通ルールの正本（rules/common-rules.md）から、PJへ書き込む版の本文を作る。

    python3 tools/build-rules.py --variant embed-both [--options autopush,worktree|none|all]   # 本文を標準出力へ

書き込み自体は tools/embed-rules.py が行う（ここは本文を作るだけ）。2026-09-26にグローバルへの
注入をやめたので、版はPJへ書き込むものだけ:
  embed-claude   PJの CLAUDE.md へ書く（Claudeだけの相手）
  embed-codex    PJの AGENTS.md へ書く（Codexだけの相手）
  embed-both     PJの AGENTS.md へ書く（既定。PJのルールを AGENTS.md に統一する）

正本の書き方:
  {{名前}}                                  版ごとの語（VARIANTS の vars）に置き換わる
  <!-- if:条件 -->…<!-- endif -->            条件が立つ版にだけ残る。行の途中にも置ける
                                            （入れ子は「行単位のブロックの中に行中の条件」だけ可）
  条件は印で書く。`,` = または、`+` = かつ、`!` = でない
    読み手: claude / codex（embed-both では両方立つ）
    個人の運用（OPTIONS）: 入れる時にPJごとに選んだものだけ立つ
  例 if:claude+codex（両方向けだけ）、if:!autopush
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

VARIANTS = {
    'embed-claude': {
        'flags': {'claude'},
        'vars': {'PJ': 'CLAUDE.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ CLAUDE.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CLAUDE_SKILL},
    },
    'embed-codex': {
        'flags': {'codex'},
        'vars': {'PJ': 'AGENTS.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ AGENTS.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CODEX_SKILL},
    },
    'embed-both': {
        'flags': {'claude', 'codex'},
        'vars': {'PJ': 'AGENTS.md', 'LIMIT_COMMON': '共通ルールのブロック', 'LIMIT_PJ': 'PJ AGENTS.md（ブロックの外）',
                 'CHECK_LIMITS': '.claude-rules/check-limits.sh', 'START_SCOPE': '共通ルール＋PJ固有',
                 'SKILL_PATH': _CLAUDE_SKILL + '（Codexは`.agents/skills/`）'},
    },
}

# 個人の運用。PJへ書き込む時にPJごとに選ぶ。
# 選ばなかった時は、正本の <!-- if:!名前 --> の文（代わりの決まり）が入るか、その決まりが無くなる。
# コミットの書き方・memory不使用・AI署名なし・§8・§9はここに入れない（全版で必須）
OPTIONS = {
    'autocommit': ('commitを指示を待たずに行う', '§5。選ばないと「commitはユーザーの指示で行う」'),
    'autopush': ('pushを事前承認なしで自動で行う', '§5。選ばないと「pushはユーザーの指示があった時だけ」'),
    'worktree': ('業務・共有リポではworktreeで作業する', '§5.1。選ばないと§5.1ごと無くなる'),
    'toolname': ('コミット・PRに内部ツール名を作業の手段として書かない', '§5.2の禁止①。選ばないと無くなる'),
}

_BLOCK = re.compile(r'^<!-- if:(\S+) -->\n(.*?)^<!-- endif -->\n', re.M | re.S)
_INLINE = re.compile(r'<!-- if:(\S+) -->(.*?)<!-- endif -->', re.S)
_VAR = re.compile(r'\{\{(\w+)\}\}')


def holds(cond: str, flags: set[str]) -> bool:
    def atom(a: str) -> bool:
        return (a[1:] not in flags) if a.startswith('!') else (a in flags)
    return any(all(atom(a) for a in term.split('+')) for term in cond.split(','))


def parse_options(text: str) -> set[str]:
    if text == 'none':
        return set()
    if text == 'all':
        return set(OPTIONS)
    chosen = {t.strip() for t in text.split(',') if t.strip()}
    unknown = chosen - set(OPTIONS)
    if unknown:
        raise ValueError(f'知らない個人の運用: {", ".join(sorted(unknown))}（--list-options で一覧）')
    return chosen


def render(variant: str, source: str | None = None, options: set[str] | None = None) -> str:
    """版の本文（マーカー行を除く）を返す。options はPJごとに選んだ個人の運用。"""
    spec = VARIANTS[variant]
    text = SOURCE.read_text(encoding='utf-8') if source is None else source
    unknown = set(options or ()) - set(OPTIONS)
    if unknown:
        raise KeyError(f'知らない個人の運用: {", ".join(sorted(unknown))}')
    flags = spec['flags'] | set(options or ())
    keep = lambda m: m.group(2) if holds(m.group(1), flags) else ''
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variant', choices=sorted(VARIANTS), required=True)
    ap.add_argument('--options', default='all', help='個人の運用（カンマ区切り / none / all。既定 all）')
    args = ap.parse_args(argv)
    sys.stdout.write(render(args.variant, options=parse_options(args.options)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
