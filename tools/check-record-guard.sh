#!/usr/bin/env bash
# check-record-guard.sh — 記録の関門（hooks/commit-record-guard.sh）が、いま効いているかを確かめる。
#
# 確かめることは2つで、別物:
#   ①スクリプトの判定が正しいか   → ここで判定する（使い捨てのリポで、記録なしのcommitを食わせる）
#   ②そのリポで発火するか         → **ここでは判定できない。**出したコマンドをBashツールで打つ
# **①が通っても②は保証されない。**スクリプトを直接叩いた結果だけで「効いている」と言うと
# 間違える（導入初日に実際にやった。IMPROVEMENTS 2026-09-18）。
# **②は単独の呼び出しで打つ。** 前に別のコマンドを繋げると、その形しだいで素通りし、
# 「効いていない」と誤って読む。偽の通過は「関門があるつもりで記録が抜ける」ので、
# **これから作業するリポで**②まで通す。
#
#   check-record-guard.sh [--hook PATH] [--repo DIR]
#     --hook  試すスクリプト（既定は ${CLAUDE_CONFIG_DIR:-~/.claude}/hooks/commit-record-guard.sh）
#     --repo  ②を試すリポ（既定はカレント）。**これから作業するリポ**を指す
#   exitは 0=①は正しい / 1=①で止めなかった / 2=準備できず中止
set -u

HOOK="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/commit-record-guard.sh"
REPO=.

while [ $# -gt 0 ]; do
  case "$1" in
    --hook) HOOK=${2:-}; shift 2 ;;
    --repo) REPO=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done

[ -r "$HOOK" ] || { echo "✗ スクリプトがありません: $HOOK（claude-rulesのinstall.shを実行してください）" >&2; exit 2; }
command -v git >/dev/null 2>&1 || { echo "✗ gitがありません" >&2; exit 2; }
top=$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null) ||
  { echo "✗ gitリポジトリではありません: $REPO" >&2; exit 2; }

# ① 使い捨てのリポで、記録なしのcommitを食わせる（このリポの中には何も作らない）
tmp=$(mktemp -d) || exit 2
trap 'rm -rf "$tmp"' EXIT
git -C "$tmp" init -q -b main || exit 2
git -C "$tmp" config user.email check@example.com
git -C "$tmp" config user.name check
printf '# 進捗\n' > "$tmp/PROGRESS.md"
git -C "$tmp" add -A >/dev/null
git -C "$tmp" commit -qm 初期 >/dev/null
printf 'x = 2\n' > "$tmp/app.py"   # 記録ではない変更だけ
git -C "$tmp" add -A >/dev/null

payload=$(printf '{"tool_name":"Bash","tool_input":{"command":"git -C %s commit -m 確認"},"cwd":"%s"}' "$tmp" "$tmp")
out=$(printf '%s' "$payload" | bash "$HOOK" 2>&1)
code=$?
if [ "$code" = 2 ]; then
  echo "① スクリプトの判定: 正しい（記録なしのcommitをexit 2で止めた）"
else
  echo "① スクリプトの判定: ✗ 止めませんでした（exit $code）" >&2
  [ -n "$out" ] && echo "$out" >&2
  echo "   $HOOK を確かめてください。" >&2
  exit 1
fi

cat <<EOS

② $top で発火するか（ここでは判定できません）
   次のコマンドを、**このセッションのBashツールで**そのまま実行してください:

     CR_RECORD_GUARD_PROBE=1 git -C $top commit --dry-run

   止まった     = このリポで関門は効いている
   結果が返った = フックが呼ばれていない。**このリポでは記録の抜けを捕まえられない**
                  （Claude Codeを再起動してもう一度。それでも通るなら、そのリポでは
                   記録を自分で確かめる）

   ※ **このコマンドだけを単独で打ってください。** 前に別のコマンドを繋げると、
      その形しだいで素通りし、「効いていない」と誤って読みます。
   ※ --dry-run なので、呼ばれなかった場合も何もコミットされません。
   ※ 入口の関門が判定できるのは「編集は前の呼び出しで済ませ、この呼び出しはcommitだけ」
      の形です。編集と一度に行う呼び出しは、判定せず「分けて打つ」ことを求めます。
      それでも通ってしまった分は、後追い（PostToolUse）が履歴を見て知らせます。
EOS
