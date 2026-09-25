#!/usr/bin/env bash
# commit-record-audit.sh — PostToolUse（Bash）フック
# **できてしまったcommitを後から見る網。** 直前のBash呼び出しでcommitが作られたら、
# そのcommitに作業の記録（REQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/）が
# 入っているかを見て、入っていなければ知らせる。
#
# なぜ要るか: 入口（PreToolUse の commit-record-guard.sh）はコマンドの実行**前**に走るので、
# 同じ呼び出しの中で書いてからcommitする形では判定できない。こちらは実行**後**に、
# コマンドの書き方によらず**gitの履歴そのもの**を見るので、見逃しが残らない。
# **止めることはできない**（commitは既にある）。できるのは、その場で気づかせること。
#
# 設計方針:
#  - fail-open。読めない・分からない時は黙る。
#  - 直近（既定120秒以内）にできたcommitだけを見る。古いHEADを蒸し返さない。
#  - 記録の方式を使っていないリポでは黙る。CLAUDE.mdは数えない（入口と同じ）。
# 登録はclaude-rules/install.shが行う（~/.claude/settings.json のPostToolUse）。
set -u

RECORD_RE='(^|/)(REQUIREMENTS|PROGRESS|NOTES)\.md$|(^|/)checkpoints/'
# pushの関門（push-record-guard.sh）と同じ例外。本文にこの行があれば、記録が要らないcommitとして黙る
EXEMPT_RE='^[[:space:]]*(記録なし|No-Record)[[:space:]]*[:：]'
FRESH_SECONDS="${CR_AUDIT_FRESH_SECONDS:-120}"

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

# 入口のフックが呼ばれているか。呼ばれていなければ、関門は配線されていない
seen_note() {
  local f="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.record-guard-seen" t now
  if [ ! -r "$f" ]; then
    echo "※ 入口のフックは一度も呼ばれていません。登録を確かめてください（install.sh）。"
    return
  fi
  t=$(cat "$f" 2>/dev/null); now=$(date +%s)
  case "$t" in ''|*[!0-9]*) return ;; esac
  echo "※ 入口のフックが最後に呼ばれたのは $(( (now - t) / 60 ))分前です。"
}

[ "$(read_json '.tool_name')" = "Bash" ] || exit 0
cmd=$(read_json '.tool_input.command')
[ -n "$cmd" ] || exit 0
# commitという語がどこにも無い呼び出しは見ない（ヒアドキュメントの中を含めて素通り）
case "$cmd" in *commit*) ;; *) exit 0 ;; esac
case "$cmd" in *CR_SKIP_RECORD_GUARD*|*CR_RECORD_GUARD_PROBE*) exit 0 ;; esac

cwd=$(read_json '.cwd')
[ -n "$cwd" ] || cwd=$PWD

# commitがどのリポにできたかは、コマンドの書き方では決まらない（cd も -C も変数も通る）。
# 実行後なので、**実際に新しいcommitを持っているリポ**を素直に探す:
#   セッションのcwd と、コマンド中に現れる実在のディレクトリ
candidates=$(
  printf '%s\n' "$cwd"
  grep -oE '(/|~/)[^[:space:]"'"'"';&|]+' <<<"$cmd" | sed "s|^~|$HOME|"
)

now=$(date +%s)
seen=
# パイプで回すと、この中のexitがサブシェルで止まって伝わらない
while IFS= read -r d; do
  [ -n "$d" ] || continue
  [ -d "$d" ] || d=$(dirname "$d")
  [ -d "$d" ] || continue
  root=$(git -C "$d" rev-parse --show-toplevel 2>/dev/null) || continue
  case " $seen " in *" $root "*) continue ;; esac
  seen="$seen $root"

  ct=$(git -C "$root" log -1 --format=%ct 2>/dev/null) || continue
  [ -n "$ct" ] || continue
  [ $((now - ct)) -lt "$FRESH_SECONDS" ] || continue   # 直前にできたcommitだけ

  git -c core.quotepath=false -C "$root" ls-files 2>/dev/null | grep -Eq "$RECORD_RE" || continue
  files=$(git -c core.quotepath=false -C "$root" show --name-only --pretty=format: HEAD 2>/dev/null)
  grep -Eq "$RECORD_RE" <<<"$files" && continue
  git -C "$root" log -1 --format=%B 2>/dev/null | grep -Eq "$EXEMPT_RE" && continue

  subject=$(git -C "$root" log -1 --format=%s 2>/dev/null)
  cat >&2 <<MSG
記録の関門（後追い）: いまできたcommitに作業の記録が入っていません。
  リポ: $root
  commit: $(git -C "$root" log -1 --format=%h) $subject

入口のフックは、書き込みとcommitが同じ呼び出しにある形では判定できません。
記録（checkpoint / PROGRESS.md / REQUIREMENTS.md / NOTES.md）を書いて、
次のcommitで入れてください。直前のcommitへまとめるなら --amend を使えます。
記録が要らない作業だった場合は、コミットメッセージに「記録なし: <理由>」を残してください
（この後追いとpushの関門は、この行を例外として通します）。
$(seen_note)
MSG
  exit 2
done < <(printf '%s\n' "$candidates")
exit 0
