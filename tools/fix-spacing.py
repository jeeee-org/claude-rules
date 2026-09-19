#!/usr/bin/env python3
"""英数字と日本語の間の半角スペース（§9の「境目の空白」）を見つけて落とす。

既存の文書へ§9を当てる時に使う。手で直すと数百行になり、その場の`sed`で当てると
行頭のマーカーや記号を挟んだ両側まで潰れる（NOTES「ルール本文の編集」2026-09-19）。

  fix-spacing.py [--write] [--keep RE]... FILE...
      既定は**検査だけ**（書かない）。直す候補と、**判断が要る候補**を分けて出す。
      --write   直す候補だけを書き戻す。判断が要る候補は触らない
      --keep RE この正規表現にあてはまる行は触らない（規則の悪い例を載せている行など）。
                何度でも指定できる

**触らないもの**
  - コードフェンス（``` ～ ```）の中と、インラインコード（`…`）の**中身**。
    境目の判定では印を透かすので、`` `install.sh` を``の空白は落ちる（中身は変わらない）
  - 行頭のマーカー（見出し記号・箇条書き・番号・チェックボックス・引用）の直後の空白
  - 行頭の日付（`- 2026-09-12 学び`）と章番号（`### 5.2 コミット`、`## 9. 応答`）の直後
  - 記号を挟んだ両側（`4軸 + checkpoint`、`やること / バックログ`）。判定の字に記号を入れないため
  - 日本語同士の空白（`記録ルールは グローバル`）。§9は英数字と日本語の境目の話なので、手で見る

**判断が要る候補**（出すだけで直さない）は2つ。
  - 日本語のうしろに`(`で始まる英語の補足が続く形（`次の一手 (Top 3)`）
  - **コード印が4つ以上並ぶ行**。記法そのものを列挙している行（`` `#`見出し `- `箇条書き ``）で、
    ここの空白は項目の区切りなので詰めると読めなくなる
詰めるかは書き手が決める。

exitは 0=直す候補なし / 1=直す候補あり（--writeなら直した） / 2=読めない等で中止。
"""
import argparse
import re
import sys
from pathlib import Path

MARK = r'(?:\*\*|\*|`|_)*'                   # 透かす印
LEFT = r'[A-Za-z0-9`)）%]'                    # 左が英数字とみなす字
RIGHT = r'[A-Za-z0-9`]'                       # 右が英数字とみなす字（開き括弧は判断が要る側へ）
JP = r'[ぁ-んァ-ヴー一-龥々〆〇、。「」『』・？！]'

ALNUM_JP = re.compile(rf'({LEFT}{MARK}) ({MARK}{JP})')
JP_ALNUM = re.compile(rf'({JP}{MARK}) ({MARK}{RIGHT})')
JP_PAREN = re.compile(rf'{JP}{MARK} {MARK}[(（][A-Za-z0-9]')   # 判断が要る候補
ENUM_SPANS = 4      # コード印がこれだけ並ぶ行は、空白が項目の区切り（記法の列挙）

# 行頭のマーカー: 引用 > / 見出し # / 箇条書き - * + （チェックボックス付き）/ 番号 1. 1)
MARKER = re.compile(r'^(\s*(?:>\s*)?(?:#{1,6}\s+|[-*+]\s+(?:\[[ x]\]\s+)?|\d+[.)]\s+)?)(.*)$')
# 本文の頭の日付・章番号（詰めると本文と地続きになる）
LEAD_KEEP = re.compile(r'^(\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)*[.)]?)( )')
CODE_SPAN = re.compile(r'(`+)(.+?)\1')
FENCE = re.compile(r'^\s*(```|~~~)')

KEEP_SPACE = ''      # 残すと決めた空白の目印
SPAN_SLOT = ''       # インラインコードの中身の目印


class Abort(Exception):
    pass


def hide_spans(line):
    """インラインコードの中身を目印に置き換える（印そのものは残す）"""
    kept = []

    def swap(m):
        kept.append(m.group(2))
        return m.group(1) + SPAN_SLOT + m.group(1)

    return CODE_SPAN.sub(swap, line), kept


def show_spans(line, kept):
    out = iter(kept)
    return CODE_SPAN.sub(lambda m: m.group(1) + next(out) + m.group(1), line)


def fix_line(line):
    """1行を直した結果と、判断が要る候補の種類（無ければNone）を返す"""
    head, body = MARKER.match(line).groups()
    body, kept = hide_spans(body)
    review = '日本語のうしろの「 (」' if JP_PAREN.search(body) else None
    body = LEAD_KEEP.sub(r'\1' + KEEP_SPACE, body)
    # 記法そのものを列挙している行では、コード印に接する空白は項目の区切りなので詰めない
    enum = len(kept) >= ENUM_SPANS
    held = []

    def join(m):
        if enum and '`' in m.group(1) + m.group(2):
            held.append(True)
            return m.group(0)
        return m.group(1) + m.group(2)

    prev = None
    while prev != body:
        prev = body
        body = ALNUM_JP.sub(join, body)
        body = JP_ALNUM.sub(join, body)
    if held:
        review = 'コード印が並ぶ行'
    body = show_spans(body.replace(KEEP_SPACE, ' '), kept)
    return head + body, review


def scan(text, keeps):
    """(直した全文, 直した行のリスト, 判断が要る行のリスト)"""
    fixed, changed, review = [], [], []
    in_fence = False
    for no, line in enumerate(text.split('\n'), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            fixed.append(line)
            continue
        if in_fence or any(k.search(line) for k in keeps):
            fixed.append(line)
            continue
        new, kind = fix_line(line)
        if kind:
            review.append((no, line, kind))
        if new != line:
            changed.append((no, line, new))
        fixed.append(new)
    if in_fence:
        raise Abort('コードフェンスが閉じていません')
    return '\n'.join(fixed), changed, review


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('files', nargs='+')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--keep', action='append', default=[])
    ap.add_argument('-h', '--help', action='store_true')
    args = ap.parse_args(argv)
    if args.help:
        print(__doc__)
        return 0

    try:
        keeps = [re.compile(k) for k in args.keep]
    except re.error as e:
        print(f'✗ --keepの正規表現が読めません: {e}', file=sys.stderr)
        return 2

    total_changed = total_review = 0
    for name in args.files:
        path = Path(name)
        try:
            src = path.read_text(encoding='utf-8')
        except OSError as e:
            print(f'✗ 読めません: {name}（{e}）', file=sys.stderr)
            return 2
        try:
            dst, changed, review = scan(src, keeps)
        except Abort as e:
            print(f'✗ {name}: {e}', file=sys.stderr)
            return 2

        for no, old, new in changed:
            print(f'{name}:{no}')
            print(f'  - {old}')
            print(f'  + {new}')
        for no, line, kind in review:
            print(f'{name}:{no}: 判断が要る（{kind}）')
            print(f'    {line}')

        total_changed += len(changed)
        total_review += len(review)
        if args.write and changed:
            path.write_text(dst, encoding='utf-8')

    verb = '直した' if args.write else '直す候補'
    print(f'{verb} {total_changed}行 / 判断が要る候補 {total_review}行')
    return 1 if total_changed and not args.write else 0


if __name__ == '__main__':
    sys.exit(main())
