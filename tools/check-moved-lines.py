#!/usr/bin/env python3
"""文書を分けて移した後、元の文書の各行が移動先のどれかに残っているかを確かめる。

既存PJを新しい記録ルールへ移す時に使う（NOTES.mdの一回限りの記録をcheckpointへ原文のまま移し、
残す節だけ書き直す、など）。本文を1行ずつ突き合わせ、どこにも無い行を出す。
出た行が「意図して書き直した・置き換えた行」だけなら、移し漏れは無い。

  check-moved-lines.py --from SOURCE TARGET...
      SOURCEは元の文書。ファイルのパスか、gitの版REV:PATH（例：HEAD:NOTES.md）。
      版を指せば、書き換える前の退避が要らない
      TARGETは移動先の候補（新しいNOTES.md・REQUIREMENTS.md・checkpoints/*.mdなど）
  オプション
      --repo DIR          REV:PATHを読むリポ（既定はカレント）。**PATHはここからの相対**として
                          解決する（モノレポのタスクで走らせてもルート直下の同名ファイルと比べない）
      --strict-headings   見出しの「#」の数まで一致を求める（既定は、段を下げて貼った見出しを同じとみなす）
      --ignore-space      行の中の空白を無視して比べる（境目の空白を補正した後に突き合わせる時。
                          補正した行が「どこにも無い」と出るのを防ぐ。先に突き合わせるのが一番確か）

比較は行頭と行末の空白を落とした完全一致（字下げを外して、または変えて移した行も同じとみなす）。
空行と、区切りだけの行（--- や |---|---|）は数えない。
exitは0=全行が残っている / 1=残っていない行がある / 2=読めない等で中止。
"""
import argparse
import posixpath
import re
import subprocess
import sys
from pathlib import Path

HEADING_RE = re.compile(r'^#{1,6}\s+')
# 水平線と、表の区切り行（| --- | :-: |）
SEPARATOR_RE = re.compile(r'^\s*(-{3,}|\*{3,}|_{3,}|\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{0,}:?\s*)\s*$')


class Abort(Exception):
    pass


def read_source(spec, repo):
    """元の文書の中身と、実際に読んだ場所を返す"""
    path = Path(spec)
    if path.is_file():
        return path.read_text(encoding='utf-8'), str(path)
    if ':' in spec:
        rev, rel = spec.split(':', 1)
        # gitはREV:PATHのPATHを**リポのルート**から解決する。モノレポのタスクで走らせると、
        # ルート直下の同名ファイルと黙って比べてしまう（関係の無い差分が大量に出る）。
        # ./を付けて--repoからの相対にし、何と比べたかを必ず出す
        git_rel = rel if rel.startswith(('./', '../')) else f'./{rel}'
        r = subprocess.run(['git', '-C', str(repo), '-c', 'core.quotepath=false', 'show', f'{rev}:{git_rel}'],
                           capture_output=True)
        if r.returncode != 0:
            raise Abort(f'{spec}をgitから読めない（{repo}から解決）: '
                        f'{r.stderr.decode("utf-8", "replace").strip()}')
        prefix = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-prefix'],
                                capture_output=True, text=True).stdout.strip()
        return r.stdout.decode('utf-8'), f'{rev}:{posixpath.normpath(posixpath.join(prefix, rel))}'
    raise Abort(f'{spec}が無い')


def key(line, strict_headings, ignore_space=False):
    # 箇条書きの続きの行は、移す先で字下げが変わることが多い（voice-inputの移行で3行が「無い」と出た）
    line = line.strip()
    if not strict_headings and HEADING_RE.match(line):
        line = 'H:' + HEADING_RE.sub('', line, count=1)
    return re.sub(r'\s+', '', line) if ignore_space else line


def counted(line):
    return line.strip() != '' and not SEPARATOR_RE.match(line)


def missing_lines(source_text, target_texts, strict_headings=False, ignore_space=False):
    haystack = {key(l, strict_headings, ignore_space) for t in target_texts for l in t.splitlines()}
    return [(n, l) for n, l in enumerate(source_text.splitlines(), 1)
            if counted(l) and key(l, strict_headings, ignore_space) not in haystack]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--from', dest='source', required=True)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--strict-headings', action='store_true')
    ap.add_argument('--ignore-space', action='store_true')
    ap.add_argument('targets', nargs='+')
    a = ap.parse_args(argv)
    try:
        source, source_shown = read_source(a.source, Path(a.repo))
        texts = []
        for t in a.targets:
            p = Path(t)
            if not p.is_file():
                raise Abort(f'移動先{t}が無い')
            texts.append(p.read_text(encoding='utf-8'))
    except Abort as e:
        print(f'中止: {e}', file=sys.stderr)
        return 2
    print(f'比較元: {source_shown}', file=sys.stderr)
    total = sum(1 for l in source.splitlines() if counted(l))
    missing = missing_lines(source, texts, a.strict_headings, a.ignore_space)
    for n, line in missing:
        print(f'{n:5d}: {line}')
    print(f'元の{total}行のうち、移動先のどこにも無い行{len(missing)}行', file=sys.stderr)
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
