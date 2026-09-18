#!/usr/bin/env bash
# check-record-guard.sh — 記録の関門（hooks/commit-record-guard.sh）が、いま効いているかを確かめる。
#
# 確かめることは2つで、別物:
#   ①スクリプト単体が止めるか   → ここで判定できる（記録なしのcommitを食わせてexit 2か見る）
#   ②このセッションで発火するか → **ここでは判定できない**。Bashツール経由でcommitして初めて分かる
# 登録は正しいのに発火しないセッションが実在する（IMPROVEMENTS 2026-09-18。条件は未特定）。
# **関門は効いていない時がいちばん危ない**ので、導入したら必ず②まで通す。
#
#   check-record-guard.sh [--hook PATH] [--dir PATH]
#     --hook  試すスクリプト（既定は ${CLAUDE_CONFIG_DIR:-~/.claude}/hooks/commit-record-guard.sh）
#     --dir   使い捨てのリポを置く場所（既定は ${TMPDIR:-/tmp}/record-guard-check）
#   exitは 0=スクリプト単体は有効 / 1=止めなかった / 2=準備できず中止
set -u

HOOK="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/commit-record-guard.sh"
DIR="${TMPDIR:-/tmp}/record-guard-check"
MARKER=.record-guard-check

while [ $# -gt 0 ]; do
  case "$1" in
    --hook) HOOK=${2:-}; shift 2 ;;
    --dir)  DIR=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "不明な引数: $1" >&2; exit 2 ;;
  esac
done

[ -r "$HOOK" ] || { echo "✗ スクリプトがありません: $HOOK（claude-rulesのinstall.shを実行してください）" >&2; exit 2; }
command -v git >/dev/null 2>&1 || { echo "✗ gitがありません" >&2; exit 2; }

# 使い捨てのリポを作り直す。自分が作った印のある場所だけを消す
if [ -e "$DIR" ] && [ ! -e "$DIR/$MARKER" ]; then
  echo "✗ $DIR は、このコマンドが作ったものではありません。--dir で別の場所を指してください。" >&2
  exit 2
fi
rm -rf "$DIR"
mkdir -p "$DIR" || exit 2
: > "$DIR/$MARKER"
git -C "$DIR" init -q -b main || exit 2
git -C "$DIR" config user.email check@example.com
git -C "$DIR" config user.name check
printf '# 進捗\n' > "$DIR/PROGRESS.md"
mkdir -p "$DIR/checkpoints"
printf '# ログ\n' > "$DIR/checkpoints/2026-01-01-疎通確認-用意.md"
git -C "$DIR" add -A >/dev/null
git -C "$DIR" commit -qm 初期 >/dev/null
# 記録ではない変更だけを載せる（この状態のcommitは止まるのが正しい）
printf 'x = 2\n' > "$DIR/app.py"
git -C "$DIR" add -A >/dev/null

TRY="git -C $DIR commit -m 疎通確認"

payload=$(printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$TRY" "$DIR")
out=$(printf '%s' "$payload" | bash "$HOOK" 2>&1)
code=$?

if [ "$code" = 2 ]; then
  echo "① スクリプト単体: 有効（記録なしのcommitをexit 2で止めた）"
else
  echo "① スクリプト単体: ✗ 止めませんでした（exit $code）" >&2
  [ -n "$out" ] && echo "$out" >&2
  echo "   $HOOK を確かめてください。" >&2
  exit 1
fi

cat <<EOS

② このセッションで発火するか（ここでは判定できません）
   次のコマンドを、**このセッションのBashツールで**そのまま実行してください:

     $TRY

   止まった   = 関門はこのセッションで効いている
   commitできた = 登録されていても発火していない。Claude Codeを再起動して、もう一度ここから

   終わったら片付け: rm -rf $DIR
EOS
