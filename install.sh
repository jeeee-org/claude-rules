#!/usr/bin/env bash
# claude-rules をローカルの Claude Code 設定に配置する。
#   rules/global-rules.md  -> $CLAUDE_CONFIG_DIR/CLAUDE.md の claude-rules ブロック（マーカー間を置換、無ければ追記）
#   skills/init-rules      -> $CLAUDE_CONFIG_DIR/skills/init-rules
# 配置先を変えたい場合: CLAUDE_CONFIG_DIR=/path/.claude ./install.sh
# 新PCでは claude-rules -> quorum -> cadence の順に install すると CLAUDE.md の並びが揃う。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

RULES_FILE="$SRC_DIR/rules/global-rules.md"
TARGET_MD="$CLAUDE_CONFIG_DIR/CLAUDE.md"

# 正本の自己検証（マーカー欠落のまま配ると注入が壊れる）
grep -q 'claude-rules:begin' "$RULES_FILE" && grep -q 'claude-rules:end' "$RULES_FILE" || {
  echo "✗ rules/global-rules.md にマーカーがありません。修正してから再実行してください。" >&2
  exit 1
}

mkdir -p "$CLAUDE_CONFIG_DIR/skills"

# init-rules スキルをコピー（正本はリポ側）
rm -rf "$CLAUDE_CONFIG_DIR/skills/init-rules"
cp -R "$SRC_DIR/skills/init-rules" "$CLAUDE_CONFIG_DIR/skills/init-rules"

# グローバル CLAUDE.md に claude-rules ブロックを注入する
# （マーカー間を置換、無ければ末尾に追記。quorum-triage / cadence-triage と同方式）
if [ -f "$TARGET_MD" ] && grep -q 'claude-rules:begin' "$TARGET_MD"; then
  awk -v rules="$RULES_FILE" '
    /claude-rules:begin/ {skip=1; while ((getline line < rules) > 0) print line; close(rules); next}
    /claude-rules:end/   {skip=0; next}
    !skip {print}
  ' "$TARGET_MD" > "$TARGET_MD.tmp" && mv "$TARGET_MD.tmp" "$TARGET_MD"
else
  { [ -s "$TARGET_MD" ] && echo ""; cat "$RULES_FILE"; } >> "$TARGET_MD"
fi
echo "  - CLAUDE.md に claude-rules ブロックを反映"

# 数値上限の目安チェック（グローバル §2。超過しても失敗にはしない）
size=$(wc -c < "$TARGET_MD")
if [ "$size" -gt 14336 ]; then
  echo "⚠ $TARGET_MD が 14KB を超過（${size} bytes）。/cadence optimize-context を検討。" >&2
fi

echo "✓ インストール完了: $CLAUDE_CONFIG_DIR"
echo "  - CLAUDE.md（claude-rules ブロック）"
echo "  - skills/init-rules"
echo ""
echo "Claude Code を再起動するか /reload-skills を実行してください。"
