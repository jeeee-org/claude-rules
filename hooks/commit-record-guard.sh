#!/usr/bin/env bash
# commit-record-guard.sh — PreToolUse（Bash）フック
# commitしようとした時に、作業の記録（REQUIREMENTS.md / PROGRESS.md / NOTES.md /
# checkpoints/）が一緒に変わっているかを見る。1つも無ければcommitを止めて差し戻す。
# グローバル§3「タスク完了時（必須）」の抜けを、自己申告から独立して捕まえるため。
#
# 設計方針:
#  - fail-open。判定できない時（jqもpython3も無い・gitの外・記録の5点を持たないリポ）は黙って通す。
#  - 禁止ではなく、意識した判断の強制。要らない時は理由を述べて
#    CR_SKIP_RECORD_GUARD=1 を付けて通す（コマンドに残るので、あとから見て分かる）。
#  - CLAUDE.mdは数えない。ルールだけを直したcommitも記録は要る。
# 登録はclaude-rules/install.shが行う（~/.claude/settings.json のPreToolUse）。
set -u

RECORD_RE='(^|/)(REQUIREMENTS|PROGRESS|NOTES)\.md$|(^|/)checkpoints/'

input=$(cat) || exit 0
[ -n "$input" ] || exit 0

# JSONの取り出し。jqが無ければpython3で代える（どちらも無ければ通す）
read_json() { # read_json <キーのパス>
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

[ "$(read_json '.tool_name')" = "Bash" ] || exit 0
cmd=$(read_json '.tool_input.command')
[ -n "$cmd" ] || exit 0

# ヒアドキュメントの中身は見ない（commitメッセージ本文にgit commitと書いてあることがある）
head_part=${cmd%%<<*}

# 本当にcommitを作ろうとしているか。git [-C path | -c k=v]... commit の形だけを拾う
grep -Eq '(^|[;&|(]|&&)[[:space:]]*git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+)*commit([[:space:]]|$)' \
  <<<"$head_part" || exit 0

# 通す指定（理由を述べたうえでの明示。コマンドに残る）
case "$cmd" in *CR_SKIP_RECORD_GUARD*) exit 0 ;; esac
# 履歴を作らない・作り直すだけのものは対象外
case "$head_part" in *--dry-run*|*--amend*) exit 0 ;; esac

cwd=$(read_json '.cwd')
[ -n "$cwd" ] || cwd=$PWD
# 先頭が cd の時はその行き先で見る（cd X && git commit ... の形）
case "$cmd" in
  cd\ *) target=${cmd#cd }; target=${target%%&&*}; target=${target%%;*}
         # evalしない（コマンド文字列をそのまま展開すると、ここが実行口になる）
         target=$(sed -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//" <<<"$target")
         case "$target" in '~'|'~/'*) target="$HOME${target#\~}" ;; esac
         [ -n "$target" ] && [ -d "$target" ] && cwd=$target ;;
esac

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$root" ] || exit 0

status=$(git -c core.quotepath=false -C "$root" status --porcelain -uall 2>/dev/null) || exit 0
[ -n "$status" ] || exit 0
changed=$(sed -e 's/^...//' -e 's/.* -> //' <<<"$status")

# このリポが記録の方式を使っているか（使っていないPJでは何も言わない）
git -c core.quotepath=false -C "$root" ls-files 2>/dev/null | grep -Eq "$RECORD_RE" ||
  grep -Eq "$RECORD_RE" <<<"$changed" || exit 0

grep -Eq "$RECORD_RE" <<<"$changed" && exit 0

cat >&2 <<'MSG'
記録の関門: このcommitに作業の記録が入っていません。
変更にREQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/のどれも含まれていません。

グローバル§3「タスク完了時（必須）」= 作業ログをその作業のcheckpointへ、PROGRESS.mdの
完了と次の一手、要件・スコープの変化をREQUIREMENTS.mdへ、学びをNOTES.mdへ。

書いてからcommitし直すか、この作業に記録が要らない理由を1行述べたうえで、
コマンドの先頭にCR_SKIP_RECORD_GUARD=1を付けて通してください。
MSG
exit 2
