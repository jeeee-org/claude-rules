#!/usr/bin/env python3
"""既存PJのcheckpointを、リポ直下の checkpoints/YYYY-MM-DD-作業内容.md の形へ揃える。

グローバル §1・§2（2026-09-12 改訂）への追従用。作業内容の名前は判断が要るのでコマンドは決めない。
対応表（TSV）を作り、人かClaudeが埋めてから apply する。ADRの仕分けも対象外。

移行は「移動」と「命名」の2つの作業で、前者だけ済んだ中間状態（docs/checkpoints/ から移してあるが
名前は YYYY-MM-DD.md のまま）が実際に生まれる。入口は移動元を見て自動で決める：
  docs/checkpoints/ に日付名のcheckpointがある → checkpoints/ へ移して改名する
  無くて checkpoints/ に日付名のものがある     → その場で改名だけする

  migrate-checkpoints.py plan  [--repo DIR] [--out names.tsv]
      対象の一覧と、見出しから拾った名前の候補を書き出す（何も動かさない）
  migrate-checkpoints.py apply --names names.tsv [--repo DIR] [--allow-dirty]
      git mv・見出しの差し替え・参照の張り直しを行い、最後に check を走らせる（commit はしない）
  migrate-checkpoints.py check [--repo DIR]
      旧パスの残りと、リンク切れを検査する（問題があれば exit 1）。見るのは
      ①docs/checkpoints/YYYY-MM-DD.md の残り ②改名前の名前のまま実在しない checkpoints/YYYY-MM-DD.md
      ③PJの中の .md から張られた相対リンクの切れ（移動で行き先がずれた外向きのリンクを含む）。
      checkpoints/ 内の旧パスは移行の記録なので①②に数えない（リンク切れは見る）。
      日付の無い旧ディレクトリへの言及（READMEの表、.gitignore のコメントなど）は、
      説明として残すこともあるので「確かめる」として出すだけにする（exit は変えない）。
      こちらは Markdown 以外も含め、git 管理下のテキストファイルすべてを見る

--repo DIR は「移すPJのディレクトリ」で、plan / apply / check とも同じ意味。git のルートでなくてよい
（モノレポの tasks/<name> など）。
参照の張り直しと検査は、そのPJのものと決まる参照だけを対象にする：
  - Markdown のリンクは、書かれたファイルの場所で解決した実パスが移動元と一致する時だけ張り直す
    （移動で1段浅くなるぶん、checkpoint から外を指す相対リンクも旧い位置で解決して張り直す）
  - 本文中の docs/checkpoints/YYYY-MM-DD.md は、書かれたファイルの場所から上へ辿り、実在する最も近い
    docs/checkpoints/ に属するとみなす。別のPJのものなら触らない（同じ日付でも別の文書）。
    tasks/<name>/docs/checkpoints/… のように場所付きで書かれたものは、その場所そのものとして扱う

対応表は1行に「日付<TAB>作業内容」。作業内容は日本語の短い語で、空白と / \\ : * ? " < > | は使えない。
# で始まる行は読み飛ばす。exit は 0=問題なし / 1=check で問題あり / 2=中止（何も変えていない）。
"""
import argparse
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

OLD_DIR = 'docs/checkpoints'
NEW_DIR = 'checkpoints'
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
NAMED_RE = re.compile(r'^\d{4}-\d{2}-\d{2}-.+')
# Markdown のリンク先。タイトル付き（空白を含む）は対象外
LINK_RE = re.compile(r'(\]\()([^)\s]+?)(#[^)\s]*)?(\))')
LINK_ANY = r'\]\([^)\s]+\)'
BAD_NAME_RE = re.compile(r'[\s/\\:*?"<>|]')
TEXT_SUFFIXES = ('.md', '.json')


def dated_re(src):
    """リンクではない本文中の、日付名のcheckpointへの言及（方式を説明する YYYY-MM-DD は残す）。

    先頭の group は場所（tasks/x/ など。素の docs/checkpoints/… なら空）
    """
    return re.compile(r'(?<![\w./-])((?:[\w.-]+/)*)' + re.escape(src) + r'/(\d{4}-\d{2}-\d{2})\.md')


def dir_only_re(src):
    """日付の有無を問わないディレクトリへの言及。日付入りは dated_re の側で数える"""
    return re.compile(r'(?<![\w./-])((?:[\w.-]+/)*)' + re.escape(src) + r'(?![\w-])')


class Abort(Exception):
    pass


class Ctx:
    """top = git のルート、rel = 移すPJのディレクトリ（ルートからの相対。ルート自身なら空）、
    src = 移す元（PJ相対。docs/checkpoints なら移動、checkpoints なら改名だけ）"""

    def __init__(self, top, rel, src=OLD_DIR):
        self.top, self.rel, self.src = top, rel, src
        self.old_dir = posixpath.join(rel, src) if rel else src
        self.new_dir = posixpath.join(rel, NEW_DIR) if rel else NEW_DIR
        self.rename_only = src == NEW_DIR
        self.dated = dated_re(src)
        self.dir_only = dir_only_re(src)
        # 本文置換の時、リンク先（rewrite_links が実パスで判断済み）は飛ばす
        self.text_or_link = re.compile(LINK_ANY + '|' + self.dated.pattern)

    def with_src(self, src):
        return Ctx(self.top, self.rel, src)

    def under(self, path):
        """リポ相対パスが移すPJの中にあるか"""
        return not self.rel or path == self.rel or path.startswith(self.rel + '/')

    def local(self, path):
        """リポ相対パスを、PJ相対（本文に書く形）にする"""
        return path[len(self.rel) + 1:] if self.rel and path.startswith(self.rel + '/') else path


def git(repo, *args):
    # 日本語のパスを 8 進エスケープさせない（core.quotepath の既定は true）
    r = subprocess.run(['git', '-C', str(repo), '-c', 'core.quotepath=false', *args], capture_output=True)
    if r.returncode != 0:
        raise Abort(f'git {" ".join(args)} が失敗: {r.stderr.decode("utf-8", "replace").strip()}')
    return r.stdout.decode('utf-8')


def tracked(ctx, suffixes=TEXT_SUFFIXES):
    return [p for p in git(ctx.top, 'ls-files', '-z').split('\0') if p.endswith(suffixes)]


def resolve_mention(f, prefix, tail, ctx, exists):
    """本文中の言及が移すPJのものなら、そのリポ相対パスを返す（違えば None）。

    場所付き（tasks/x/docs/checkpoints/…）はその場所そのもの。素の docs/checkpoints/… は、書かれた
    ファイルの場所から上へ辿り、実在する最も近い docs/checkpoints/ に属するとみなす（モノレポで、別の
    PJの同じ日付の記録が本体の新パスへ化けた事故への対策）。
    """
    target = posixpath.normpath(ctx.old_dir + tail)
    if prefix:
        return target if posixpath.normpath(prefix + ctx.src + tail) == target else None
    d = posixpath.dirname(f)
    while True:
        cand = posixpath.normpath(posixpath.join(d, ctx.src + tail))
        if cand == target:
            return target
        if exists(cand):
            return None  # 別のPJの記録
        if d in ('', '.'):
            break
        d = posixpath.dirname(d)
    return target if ctx.under(f) else None


def is_external(target):
    return target.startswith(('/', '#')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target) is not None


def old_checkpoints(ctx):
    """移す元の中身を、日付名のもの／改名済みのもの／それ以外に分ける"""
    d = ctx.top / ctx.old_dir
    if not d.is_dir():
        return [], [], []
    dated, done, others = [], [], []
    for p in sorted(d.iterdir()):
        if p.suffix == '.md' and DATE_RE.match(p.stem):
            dated.append(p)
        elif ctx.rename_only and p.suffix == '.md' and NAMED_RE.match(p.stem):
            done.append(p)
        else:
            others.append(p)
    return dated, done, others


def pick_ctx(top, rel):
    """移す元を決める。docs/checkpoints/ にあれば移動、無くて checkpoints/ にあれば改名だけ"""
    move, rename = Ctx(top, rel, OLD_DIR), Ctx(top, rel, NEW_DIR)
    if old_checkpoints(move)[0]:
        return move, len(old_checkpoints(rename)[0])
    if old_checkpoints(rename)[0]:
        return rename, 0
    raise Abort(f'{move.old_dir}/ にも {rename.new_dir}/ にも、日付名（YYYY-MM-DD.md）のcheckpointが無い')


def announce(ctx, dated, left):
    if ctx.rename_only:
        print(f'改名だけ: {ctx.old_dir}/ の日付名 {len(dated)} 件（移動は済んでいる）', file=sys.stderr)
    else:
        print(f'移動と改名: {ctx.old_dir}/ の {len(dated)} 件を {ctx.new_dir}/ へ', file=sys.stderr)
    if left:
        print(f'※ {ctx.new_dir}/ にも日付名のままの {left} 件がある。この回のあと、もう一度 plan → apply で改名する',
              file=sys.stderr)


def guess_name(path):
    """見出しから作業内容の候補を拾う。決めるのは人（空でもよい）"""
    for line in path.read_text(encoding='utf-8').splitlines():
        m = re.match(r'^#{1,3}\s+(.+)', line)
        if not m:
            continue
        t = re.sub(r'^\d{4}-\d{2}-\d{2}', '', m.group(1)).strip()
        if t in ('', '作業ログ', 'checkpoint'):
            continue
        return BAD_NAME_RE.sub('', t)[:30]
    return ''


def load_names(path, dated, ctx):
    names = {}
    for n, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) != 2:
            raise Abort(f'{path}:{n}: 「日付<TAB>作業内容」の形になっていない')
        date, name = parts[0].strip(), parts[1].strip()
        if not DATE_RE.match(date):
            raise Abort(f'{path}:{n}: 日付の形ではない: {date}')
        if not name:
            raise Abort(f'{path}:{n}: {date} の作業内容が空')
        if BAD_NAME_RE.search(name):
            raise Abort(f'{path}:{n}: {date} の作業内容に使えない文字がある（空白と / \\ : * ? " < > |）: {name}')
        if date in names:
            raise Abort(f'{path}:{n}: {date} が2回ある')
        names[date] = name
    want = {p.stem for p in dated}
    missing, extra = sorted(want - names.keys()), sorted(names.keys() - want)
    if missing:
        raise Abort('対応表に無い日付がある: ' + ', '.join(missing))
    if extra:
        raise Abort(f'{ctx.old_dir}/ に無い日付が対応表にある: ' + ', '.join(extra))
    return names


def rewrite_links(text, old_file, new_file, moves, ctx):
    """リンク先を旧い位置で解決し、移動後の位置から張り直す（実パスが移動元と一致する時だけ）"""
    old_dir, new_dir = posixpath.dirname(old_file), posixpath.dirname(new_file)

    def repl(m):
        target = m.group(2)
        if is_external(target):
            return m.group(0)
        resolved = posixpath.normpath(posixpath.join(old_dir, unquote(target)))
        # ディレクトリそのものへのリンク（READMEの「記録の置き場」の表など）も新しい置き場へ
        dest = ctx.new_dir if resolved == ctx.old_dir else moves.get(resolved, resolved)
        if dest == resolved and old_dir == new_dir:
            return m.group(0)
        slash = '/' if target.endswith('/') else ''
        return f'{m.group(1)}{posixpath.relpath(dest, new_dir or ".")}{slash}{m.group(3) or ""}{m.group(4)}'

    return LINK_RE.sub(repl, text)


def rewrite_text(text, f, moves, ctx, exists):
    """リンクでない本文の旧パスを、移すPJのものと決まる場合だけ書き換える"""
    def repl(m):
        if m.group(0).startswith(']('):
            return m.group(0)
        prefix, date = m.group(1), m.group(2)
        old = resolve_mention(f, prefix, f'/{date}.md', ctx, exists)
        if old not in moves:
            return m.group(0)
        return moves[old] if prefix else ctx.local(moves[old])

    return ctx.text_or_link.sub(repl, text)


def retitle(text, date, name):
    first, sep, rest = text.partition('\n')
    if re.fullmatch(rf'#\s+{re.escape(date)}(\s+(作業ログ|checkpoint))?\s*', first):
        return f'# {date} {name}{sep}{rest}'
    return text


def cmd_plan(ctx, left, out):
    dated, done, others = old_checkpoints(ctx)
    announce(ctx, dated, left)
    text = '# 日付<TAB>作業内容。候補は見出しから拾っただけなので直す（空白と / などは使えない）\n'
    text += ''.join(f'{p.stem}\t{guess_name(p)}\n' for p in dated)
    if out:
        Path(out).write_text(text, encoding='utf-8')
        print(f'{out} に {len(dated)} 件を書いた', file=sys.stderr)
    else:
        sys.stdout.write(text)
    if done:
        print(f'改名済みなので触らない: {len(done)} 件', file=sys.stderr)
    for p in others:
        print(f'日付名でないので移さない: {p.relative_to(ctx.top).as_posix()}', file=sys.stderr)
    return 0


def cmd_apply(ctx, left, names_path, allow_dirty):
    dated, done, others = old_checkpoints(ctx)
    announce(ctx, dated, left)
    names = load_names(names_path, dated, ctx)
    if not allow_dirty and git(ctx.top, 'status', '--porcelain').strip():
        raise Abort('作業ツリーに未コミットの変更がある。commit してから流す（--allow-dirty で無視）')
    moves = {f'{ctx.old_dir}/{d}.md': f'{ctx.new_dir}/{d}-{n}.md' for d, n in names.items()}
    all_tracked = set(tracked(ctx, suffixes=''))
    untracked = sorted(set(moves) - all_tracked)
    if untracked:
        raise Abort('git 管理外の旧checkpointがある（先に add する）: ' + ', '.join(untracked))
    clash = [n for n in moves.values() if (ctx.top / n).exists()]
    if clash:
        raise Abort('移動先が既にある: ' + ', '.join(clash))

    # 参照はリポ全体から探す（別のPJが場所付きで引いていることがある）。実パスで判断するので他のPJの記録は触らない
    before = {f: (ctx.top / f).read_text(encoding='utf-8') for f in tracked(ctx) if (ctx.top / f).is_file()}
    (ctx.top / ctx.new_dir).mkdir(exist_ok=True)
    for old, new in moves.items():
        git(ctx.top, 'mv', old, new)
    edited = []
    for f, text in before.items():
        new_f = moves.get(f, f)
        out = rewrite_links(text, f, new_f, moves, ctx) if f.endswith('.md') else text
        out = rewrite_text(out, f, moves, ctx, all_tracked.__contains__)
        if new_f != f:
            date = posixpath.basename(f)[:-len('.md')]
            out = retitle(out, date, names[date])
        if out != text:
            (ctx.top / new_f).write_text(out, encoding='utf-8')
            edited.append(new_f)
    if not ctx.rename_only and not others:
        try:
            (ctx.top / ctx.old_dir).rmdir()
        except OSError:
            pass
    print(f'{"改名" if ctx.rename_only else "移動"} {len(moves)} 件 / 書き換え {len(edited)} ファイル')
    for f in edited:
        print(f'  書き換え: {f}')
    if done:
        print(f'改名済みなので触らなかった: {len(done)} 件', file=sys.stderr)
    for p in others:
        print(f'日付名でないので残した: {p.relative_to(ctx.top).as_posix()}', file=sys.stderr)
    return cmd_check(ctx)


def read_text(path):
    """テキストなら中身を、バイナリ（先頭に NUL がある）なら None を返す"""
    data = path.read_bytes()
    if b'\0' in data[:8192]:
        return None
    return data.decode('utf-8', errors='replace')


def cmd_check(ctx):
    problems, mentions = [], []
    all_tracked = set(tracked(ctx, suffixes=''))
    moved, renamed = ctx.with_src(OLD_DIR), ctx.with_src(NEW_DIR)

    def has_file(p):
        return p in all_tracked

    def has_dir(p):
        return any(t.startswith(p + '/') for t in all_tracked)

    def dated_mentions(text, f, c):
        for m in c.text_or_link.finditer(text):
            if m.group(0).startswith(']('):  # リンクはリンク切れの側で見る
                continue
            target = resolve_mention(f, m.group(1), f'/{m.group(2)}.md', c, has_file)
            if target:
                yield m.group(0), target

    for f in sorted(all_tracked):
        p = ctx.top / f
        if not p.is_file():
            continue
        text = read_text(p)
        if text is None:
            continue
        if not f.startswith(f'{ctx.new_dir}/'):  # checkpoint は追記専用の記録。旧パスを書いた対応表などは正しい
            if f.endswith(TEXT_SUFFIXES):
                # 移すPJのものと決まる言及だけ。別のPJの docs/checkpoints/ は、そのPJを移す時に見る
                problems += [f'{f}: 旧パスが残っている: {s}' for s, _ in dated_mentions(text, f, moved)]
                # 移動は済んだが名前が古いままの言及。まだ改名していないPJでは正しい参照なので、実在しない分だけ
                problems += [f'{f}: 改名前の名前のまま残っている: {s}'
                             for s, t in dated_mentions(text, f, renamed) if not has_file(t)]
            for m in moved.dir_only.finditer(text):
                if moved.dated.match(text, m.start()) and f.endswith(TEXT_SUFFIXES):
                    continue
                if resolve_mention(f, m.group(1), '', moved, has_dir) is None:
                    continue
                line_no = text.count('\n', 0, m.start()) + 1
                line = text.splitlines()[line_no - 1].strip()
                mentions.append(f'{f}:{line_no}: {line}')
        if not f.endswith('.md'):
            continue
        for m in LINK_RE.finditer(text):
            target = m.group(2)
            if is_external(target):
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(f), unquote(target)))
            if resolved.startswith('..') or (ctx.top / resolved).exists():
                continue  # リポの外へ出る行き先は、この木からは判断しない
            if re.search(r'(^|/)checkpoints/', resolved) and (ctx.under(resolved) or ctx.under(f)):
                problems.append(f'{f}: checkpointへのリンクが切れている: {target}')
            elif ctx.under(f) and resolved.endswith('.md'):
                # 移動で1段浅くなり、外を指す相対リンクの行き先がずれたもの（手で移した時に起きる）
                problems.append(f'{f}: リンクが切れている: {target}')
    if mentions:
        print('確かめる: 旧ディレクトリへの言及（説明として残すもの以外は直す）')
        print('\n'.join(f'  {m}' for m in mentions))
    if problems:
        print('\n'.join(problems))
        return 1
    print('check: 旧パスの残りも、リンク切れも無い')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('plan', 'apply', 'check'):
        s = sub.add_parser(name)
        s.add_argument('--repo', default='.', help='移すPJのディレクトリ（モノレポのサブディレクトリ可。git のルートでなくてよい）')
        if name == 'plan':
            s.add_argument('--out')
        if name == 'apply':
            s.add_argument('--names', required=True)
            s.add_argument('--allow-dirty', action='store_true')
    a = ap.parse_args(argv)
    try:
        base = Path(a.repo)
        if not base.is_dir():
            raise Abort(f'--repo のディレクトリが無い: {a.repo}')
        top = Path(git(base, 'rev-parse', '--show-toplevel').strip()).resolve()
        rel = base.resolve().relative_to(top).as_posix()
        rel = '' if rel == '.' else rel
        if a.cmd == 'check':
            return cmd_check(Ctx(top, rel))
        ctx, left = pick_ctx(top, rel)
        if a.cmd == 'plan':
            return cmd_plan(ctx, left, a.out)
        return cmd_apply(ctx, left, a.names, a.allow_dirty)
    except Abort as e:
        print(f'中止: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
