#!/usr/bin/env bash
# push-record-guard.sh — PreToolUse（Bash）フック。**記録の関門の本丸。**
# pushしようとした時に、これから押し出すcommitを1つずつ見て、作業の記録
# （REQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/）が入っていないものがあれば止める。
#
# なぜpushなのか: commitの時点は、**判定に必要な情報が揃っていない唯一の時点**だった。
# PreToolUseは実行前なので書き込みが見えず、PostToolUseは既にできていて止められない。
# pushの直前なら**commitはもう存在する**ので、コマンドの書き方に一切依存せず正確に判定でき、
# しかもまだ止められる。グローバル§5は「commitに続けて自動push」なので、効きはcommitを
# 止めるのとほぼ同じで、直し方は軽い（--amend か、記録のcommitを足して押し直す）。
#
# 例外は**コミットメッセージのトレーラ**で持つ:
#   記録なし: <理由>      （英語なら No-Record: <理由>）
# コマンドに書く指定と違い、**理由が履歴に残って後から数えられる**。
#
# 設計方針:
#  - fail-open。判定できない時（gitの外・リモートが無い・記録の方式を使っていないリポ・
#    jqもpython3も無い）は黙って通す。
#  - **押し出す数が多い時（既定20件超）は黙って通す。** 作りたてのリポの初回pushは、
#    記録の方式より前のcommitを含むので、そこで止めても直しようがない。
#  - マージcommitは見ない（中身は元のcommitで見ている）。
# 登録はclaude-rules/install.shが行う（~/.claude/settings.json のPreToolUse）。
set -u

RECORD_RE='(^|/)(REQUIREMENTS|PROGRESS|NOTES)\.md$|(^|/)checkpoints/'
EXEMPT_RE='^[[:space:]]*(記録なし|No-Record)[[:space:]]*[:：]'
MAX_COMMITS="${CR_PUSH_MAX_COMMITS:-20}"
PATH_PAT='("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]+)'
GIT_PUSH_RE='git[[:space:]]+((-C|-c)[[:space:]]+'"$PATH_PAT"'[[:space:]]+)*push'
SEEN_FILE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.record-guard-seen"

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
# 入口のフックが呼ばれた印（配線が生きているかを、あとから観測値として読むため）
{ date +%s > "$SEEN_FILE"; } 2>/dev/null || true

cmd=$(read_json '.tool_input.command')
[ -n "$cmd" ] || exit 0
head_part=$(strip_heredoc_bodies <<<"$cmd")

grep -Eq "(^|[;&|(]|&&)[[:space:]]*${GIT_PUSH_RE}([[:space:]]|\$)" <<<"$head_part" || exit 0
case "$head_part" in *CR_SKIP_RECORD_GUARD*) exit 0 ;; esac
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
git -c core.quotepath=false -C "$root" ls-files 2>/dev/null | grep -Eq "$RECORD_RE" || exit 0

# これから押し出すcommit＝どのリモートからも辿れないもの。upstreamの有無に依存しない
[ -n "$(git -C "$root" remote 2>/dev/null)" ] || exit 0
mapfile -t commits < <(git -C "$root" log --format=%H --no-merges HEAD --not --remotes 2>/dev/null)
[ "${#commits[@]}" -gt 0 ] || exit 0
[ "${#commits[@]}" -le "$MAX_COMMITS" ] || exit 0   # 初回pushなどは対象外

bad=""
for sha in "${commits[@]}"; do
  msg=$(git -C "$root" log -1 --format=%B "$sha" 2>/dev/null)
  grep -Eq "$EXEMPT_RE" <<<"$msg" && continue          # 理由付きの例外（履歴に残る）
  files=$(git -c core.quotepath=false -C "$root" show --name-only --pretty=format: "$sha" 2>/dev/null)
  grep -Eq "$RECORD_RE" <<<"$files" && continue
  bad="$bad$(git -C "$root" log -1 --format='  %h %s' "$sha")
"
done
[ -n "$bad" ] || exit 0

cat >&2 <<MSG
記録の関門: 押し出そうとしているcommitに、作業の記録が入っていないものがあります。
  リポ: $root

$bad
記録（その作業のcheckpoint / PROGRESS.mdの完了と次の一手 / REQUIREMENTS.mdの要件の変化 /
NOTES.mdの学び）を書いて、直前のcommitへまとめる（--amend）か、記録のcommitを足してから
押し直してください。

記録が要らない作業だった場合は、**コミットメッセージに理由を残して**ください:
  記録なし: <なぜ要らないか（例：空白の整形のみ）>
コマンドに付ける指定と違い、この形なら理由が履歴に残り、あとから数えられます。

このコマンドは1行も実行されていません。
MSG
exit 2
