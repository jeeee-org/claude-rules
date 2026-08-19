#!/usr/bin/env bash
# 複数PC間の claude-rules のズレを調べるための状態採取スクリプト。
#
# push 権限の無いPCで実行し、出力をそのまま貼って上流PCへ渡す用途。
#   bash tools/collect-state.sh [ラベル]
#
# 出力は ~/claude-rules-state.txt にも保存する。
# $HOME は ~ に伏せる。settings.json の中身は出さない（件数のみ）。
set -uo pipefail

LABEL="${1:-unnamed-pc}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # 正本の所在（subtree 配下でも可）
CC="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CX="${CODEX_HOME:-$HOME/.codex}"
OUT="$HOME/claude-rules-state.txt"

# 正本として比較する対象（install.sh が配るものと対応）
FILES="rules/global-rules.md rules/codex-global-rules.md install.sh
hooks/triage-classifier.sh hooks/codex-triage.sh hooks/triage-rubric.txt
skills/init-rules/SKILL.md skills/codex-init-rules/SKILL.md
skills/codex-triage/SKILL.md skills/codex-triage/agents/openai.yaml
tools/collect-state.sh README.md CLAUDE.md"

hide() { sed "s#$HOME#~#g"; }

{
echo "### label       $LABEL"
echo "### root        $(echo "$ROOT" | hide)"

echo "### git"
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "  toplevel  $(git -C "$ROOT" rev-parse --show-toplevel | hide)"
  echo "  head      $(git -C "$ROOT" log --oneline -1 2>/dev/null)"
  echo "  origin    $(git -C "$ROOT" remote get-url origin 2>/dev/null || echo '(なし)')"
  echo "  dirty(claude-rules配下のみ)"
  git -C "$ROOT" status --porcelain=v1 -- "$ROOT" 2>/dev/null | hide | sed 's/^/    /'
  echo "  subtree-merges"
  git -C "$ROOT" log --oneline --grep='claude-rules' --max-count=5 2>/dev/null | sed 's/^/    /'
else
  echo "  (git 管理外)"
fi

echo "### hashes  ※上流の基準値と突き合わせる"
for f in $FILES; do
  if [ -f "$ROOT/$f" ]; then
    printf "  %s  %s\n" "$(sha256sum "$ROOT/$f" | cut -c1-12)" "$f"
  else
    printf "  %-12s  %s\n" "-なし-" "$f"
  fi
done

echo "### drift  正本 vs 生成物（差分があれば手編集された証拠）"
for pair in "rules/global-rules.md|$CC/CLAUDE.md|claude-rules" \
            "rules/codex-global-rules.md|$CX/AGENTS.md|codex-rules"; do
  IFS='|' read -r src dst marker <<<"$pair"
  echo "  -- $marker"
  if [ ! -f "$ROOT/$src" ]; then echo "     正本なし"; continue; fi
  if [ ! -f "$dst" ]; then echo "     生成物なし: $(echo "$dst" | hide)"; continue; fi
  awk "/${marker}:begin/,/${marker}:end/" "$dst" > "/tmp/_crs_$marker" 2>/dev/null
  if diff -q "$ROOT/$src" "/tmp/_crs_$marker" >/dev/null 2>&1; then
    echo "     一致"
  else
    echo "     DRIFT ↓"
    diff -u "$ROOT/$src" "/tmp/_crs_$marker" | tail -n +3 | head -60 | sed 's/^/     /'
  fi
  rm -f "/tmp/_crs_$marker"
done

echo "### blocks  常時ロードされるファイルのブロック構成と並び"
for f in "$CC/CLAUDE.md" "$CX/AGENTS.md"; do
  echo "  -- $(echo "$f" | hide)  $( [ -f "$f" ] && wc -c < "$f" || echo 0 )B"
  [ -f "$f" ] && grep -n ':begin\|:end' "$f" | sed 's/ (.*//' | sed 's/^/     /'
done

echo "### installed  配置物の一覧"
for d in "$CC/skills" "$CC/hooks" "$CX/skills" "$CX/hooks"; do
  echo "  -- $(echo "$d" | hide)"
  [ -d "$d" ] && ls -1 "$d" 2>/dev/null | sed 's/^/     /'
done

echo "### hook-enabled  triage-classifier の settings.json 登録（件数のみ）"
n=$(grep -c 'triage-classifier' "$CC/settings.json" 2>/dev/null) || true
echo "  ${n:-0}"

echo "### pj-limits  カレントPJの常時ロードファイル（グローバル §2 の上限確認）"
for f in CLAUDE.md AGENTS.md PROGRESS.md; do
  [ -f "$PWD/$f" ] && printf "  %-12s %6sB %4s行\n" "$f" "$(wc -c < "$f")" "$(wc -l < "$f")"
done
} 2>&1 | tee "$OUT"

echo
echo "→ $(echo "$OUT" | sed "s#$HOME#~#g") にも保存しました。この出力を丸ごと貼ってください。"
