#!/usr/bin/env bash
# push-attribution-guard.sh — PreToolUse（Bash）フック
# pushの直前に、これから押し出すcommitのメッセージを1本ずつ見て、AI帰属行
# （Co-Authored-By: Claude... / 🤖 Generated with... / noreply@anthropic.com）が
# 入っているものがあれば止める。グローバル§5.2禁止②を、自己申告から独立して担保する。
#
# なぜpushなのか（hooks/push-record-guard.shと同じ理由）:
#   commitの時点は、メッセージの渡し方（-m / -F file / エディタ / ヒアドキュメント）に
#   依存して中身が見えない。pushの直前ならcommitはもう存在するので、書き方に一切依存せず
#   読める。しかもまだ --amendで直せる（未pushなのでforceは要らない）。押してしまうと、
#   共有ブランチへのforce pushという重い手当てになる（2026-09-20に実際に起きた）。
#
# なぜ要るのか:
#   セッション側から「commitの末尾にCo-Authored-Byを付けよ」という指示が渡ることがある。
#   規約が勝つ側だが、その判断をモデルに委ねている限り取りこぼす。
#
# 設計方針:
#  - fail-open。判定できない時（gitの外・リモートが無い・jqもpython3も無い）は黙って通す。
#  - 既定で全リポを対象にする。規約上は「個人リポでは任意」だが、claude-rules自身も
#    「付けない」方針なので、既定を厳しくして脱出弁を1つ置くほうが単純。
#  - 例外はコマンド側の指定のみ（CR_SKIP_ATTRIBUTION_GUARD=1）。**メッセージのトレーラでは
#    抜けられない** —— ここで問題にしているのはメッセージそのものなので、そこに例外を
#    置くと堂々巡りになる（記録の関門とはこの点が違う）。
set -u

# 署名の形をしたものだけを見る。本文に「Claude」と書くこと自体は止めない
# （Botの応答について書いたcommitが作れなくなる）。照合前に小文字化する。
ATTR_RE='^[[:space:]]*co-authored-by:.*(claude|anthropic)|noreply@anthropic\.com|generated with.*claude|^[[:space:]]*🤖'
MAX_COMMITS="${CR_PUSH_MAX_COMMITS:-50}"
PATH_PAT='("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]+)'
GIT_PUSH_RE='git[[:space:]]+((-C|-c)[[:space:]]+'"$PATH_PAT"'[[:space:]]+)*push'

input=$(cat) || exit 0
[ -n "$input" ] || exit 0

read_json() {
  if command -v jq >/dev/null 2>&1; then
    jq -r "$1 // empty" <<<"$input" 2>/dev/null
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
for k in sys.argv[1].lstrip(".").split("."):
    d = d.get(k) if isinstance(d, dict) else None
print(d if isinstance(d,str) else "")' "$1" <<<"$input" 2>/dev/null
  fi
}

unquote() { sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"; }
expand_home() { case "$1" in '~'|'~/'*) printf '%s' "$HOME${1#\~}" ;; *) printf '%s' "$1" ;; esac; }

# ヒアドキュメントの本体だけを落とす（`<<`から後ろを切ると、その後ろのpushが漏れる）
strip_heredoc_bodies() {
  awk '
    function delim_of(line,   tmp, d, delim) {
      tmp = line; gsub(/<<</, "\001", tmp); delim = ""
      while (match(tmp, /<<-?[ \t]*("[^"]+"|\047[^\047]+\047|[A-Za-z_][A-Za-z0-9_]*)/)) {
        d = substr(tmp, RSTART, RLENGTH); sub(/^<<-?[ \t]*/, "", d); gsub(/["\047]/, "", d)
        delim = d; tmp = substr(tmp, RSTART + RLENGTH)
      }
      return delim
    }
    { if (skip != "") { t = $0; sub(/^[ \t]+/, "", t); if (t == skip) skip = ""; next }
      print; skip = delim_of($0) }
  '
}

[ "$(read_json '.tool_name')" = "Bash" ] || exit 0

cmd=$(read_json '.tool_input.command')
[ -n "$cmd" ] || exit 0
head_part=$(strip_heredoc_bodies <<<"$cmd")

grep -Eq "(^|[;&|(]|&&)[[:space:]]*${GIT_PUSH_RE}([[:space:]]|\$)" <<<"$head_part" || exit 0
case "$head_part" in *CR_SKIP_ATTRIBUTION_GUARD*) exit 0 ;; esac
case "$head_part" in *--dry-run*|*--delete*) exit 0 ;; esac

cwd=$(read_json '.cwd')
[ -n "$cwd" ] || cwd=$PWD
case "$head_part" in
  cd\ *) target=$(sed -e 's/&&.*//' -e 's/;.*//' <<<"${head_part#cd }" | unquote)
         target=$(expand_home "$target")
         [ -n "$target" ] && [ -d "$target" ] && cwd=$target ;;
esac
git_call=$(grep -oE "$GIT_PUSH_RE" <<<"$head_part" | tail -n1)
repo_opt=$(grep -oE -- "-C[[:space:]]+$PATH_PAT" <<<"$git_call" | tail -n1 | sed 's/^-C//' | unquote)
if [ -n "$repo_opt" ]; then
  repo_opt=$(expand_home "$repo_opt")
  case "$repo_opt" in /*) ;; *) repo_opt="$cwd/$repo_opt" ;; esac
  [ -d "$repo_opt" ] || exit 0
  cwd=$repo_opt
fi

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$root" ] || exit 0

# これから押し出すcommit＝どのリモートからも辿れないもの。upstreamの有無に依存しない
[ -n "$(git -C "$root" remote 2>/dev/null)" ] || exit 0
mapfile -t commits < <(git -C "$root" log --format=%H --no-merges HEAD --not --remotes 2>/dev/null)
[ "${#commits[@]}" -gt 0 ] || exit 0
[ "${#commits[@]}" -le "$MAX_COMMITS" ] || exit 0

bad=""
for sha in "${commits[@]}"; do
  hits=$(git -C "$root" log -1 --format=%B "$sha" 2>/dev/null \
         | tr 'A-Z' 'a-z' | grep -nE "$ATTR_RE" | head -n 3)
  [ -n "$hits" ] || continue
  bad="$bad$(git -C "$root" log -1 --format='  %h %s' "$sha")
$(sed 's/^/      /' <<<"$hits")
"
done
[ -n "$bad" ] || exit 0

cat >&2 <<MSG
AI帰属行の関門: 押し出そうとしているcommitのメッセージに、AI帰属行が入っています。
  リポ: $root

$bad
グローバル§5.2禁止②（業務/共有リポではClaude / AI系の署名・宣伝行を書かない）に当たります。
**セッション側から付けよという指示が渡っていても、この規約が勝ちます。**

直し方（まだpushしていないので、forceは要りません）:
  直近の1本  : git -C "$root" commit --amend
  それより前 : git -C "$root" rebase --exec \\
                 'git log -1 --format=%B | grep -viE "co-authored-by:.*(claude|anthropic)|noreply@anthropic\.com|generated with.*claude|^[[:space:]]*🤖" | git commit --amend -F -' \\
                 <押していない範囲の1つ手前>

このコマンドは1行も実行されていません。
MSG
exit 2
