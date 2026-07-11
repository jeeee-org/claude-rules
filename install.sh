#!/usr/bin/env bash
# claude-rules をローカルの Claude Code / Codex 設定に配置する。
#   rules/global-rules.md       -> $CLAUDE_CONFIG_DIR/CLAUDE.md
#   rules/codex-global-rules.md -> $CODEX_HOME/AGENTS.md
#   skills/* と hooks/*         -> 各環境の対応ディレクトリ
# 配置先を変えたい場合:
#   CLAUDE_CONFIG_DIR=/path/.claude CODEX_HOME=/path/.codex ./install.sh
# 複数PCへの事前配布を可能にするため、CLI未導入でも両設定ディレクトリを作る。
# 新PCでは claude-rules -> quorum -> cadence の順に install すると CLAUDE.md の並びが揃う。
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

RULES_FILE="$SRC_DIR/rules/global-rules.md"
TARGET_MD="$CLAUDE_CONFIG_DIR/CLAUDE.md"
CODEX_RULES_FILE="$SRC_DIR/rules/codex-global-rules.md"
CODEX_TARGET_MD="$CODEX_HOME/AGENTS.md"

# 正本の自己検証（マーカー欠落のまま配ると注入が壊れる）
grep -q 'claude-rules:begin' "$RULES_FILE" && grep -q 'claude-rules:end' "$RULES_FILE" || {
  echo "✗ rules/global-rules.md にマーカーがありません。修正してから再実行してください。" >&2
  exit 1
}
grep -q 'codex-rules:begin' "$CODEX_RULES_FILE" && grep -q 'codex-rules:end' "$CODEX_RULES_FILE" || {
  echo "✗ rules/codex-global-rules.md にマーカーがありません。" >&2
  exit 1
}

mkdir -p "$CLAUDE_CONFIG_DIR/skills"

# init-rules スキルをコピー（正本はリポ側）
rm -rf "$CLAUDE_CONFIG_DIR/skills/init-rules"
cp -R "$SRC_DIR/skills/init-rules" "$CLAUDE_CONFIG_DIR/skills/init-rules"

mkdir -p "$CODEX_HOME/skills"
rm -rf "$CODEX_HOME/skills/init-rules"
cp -R "$SRC_DIR/skills/codex-init-rules" "$CODEX_HOME/skills/init-rules"
rm -rf "$CODEX_HOME/skills/triage"
cp -R "$SRC_DIR/skills/codex-triage" "$CODEX_HOME/skills/triage"

# トリアージ分類フックをコピー（settings.json への登録は opt-in。末尾の案内参照）
mkdir -p "$CLAUDE_CONFIG_DIR/hooks"
cp "$SRC_DIR/hooks/triage-classifier.sh" "$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh"
cp "$SRC_DIR/hooks/triage-rubric.txt" "$CLAUDE_CONFIG_DIR/hooks/triage-rubric.txt"
chmod +x "$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh"

mkdir -p "$CODEX_HOME/hooks"
cp "$SRC_DIR/hooks/codex-triage.sh" "$CODEX_HOME/hooks/codex-triage"
cp "$SRC_DIR/hooks/triage-rubric.txt" "$CODEX_HOME/hooks/triage-rubric.txt"
chmod +x "$CODEX_HOME/hooks/codex-triage"

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

if [ -f "$CODEX_TARGET_MD" ] && grep -q 'codex-rules:begin' "$CODEX_TARGET_MD"; then
  awk -v rules="$CODEX_RULES_FILE" '
    /codex-rules:begin/ {skip=1; while ((getline line < rules) > 0) print line; close(rules); next}
    /codex-rules:end/   {skip=0; next}
    !skip {print}
  ' "$CODEX_TARGET_MD" > "$CODEX_TARGET_MD.tmp" && mv "$CODEX_TARGET_MD.tmp" "$CODEX_TARGET_MD"
else
  { [ -s "$CODEX_TARGET_MD" ] && echo ""; cat "$CODEX_RULES_FILE"; } >> "$CODEX_TARGET_MD"
fi
echo "  - Codex AGENTS.md に codex-rules ブロックを反映"

# 数値上限の目安チェック（グローバル §2。超過しても失敗にはしない）
size=$(wc -c < "$TARGET_MD")
if [ "$size" -gt 14336 ]; then
  echo "⚠ $TARGET_MD が 14KB を超過（${size} bytes）。/cadence optimize-context を検討。" >&2
fi
codex_size=$(wc -c < "$CODEX_TARGET_MD")
if [ "$codex_size" -gt 14336 ]; then
  echo "⚠ $CODEX_TARGET_MD が 14KB を超過（${codex_size} bytes）。" >&2
fi

echo "✓ インストール完了: $CLAUDE_CONFIG_DIR"
echo "  - CLAUDE.md（claude-rules ブロック）"
echo "  - skills/init-rules"
echo "  - hooks/triage-classifier.sh（コピーのみ。有効化は下記 opt-in）"
echo "  - $CODEX_TARGET_MD（codex-rules ブロック）"
echo "  - $CODEX_HOME/skills/init-rules"
echo "  - $CODEX_HOME/skills/triage（自然言語での明示トリアージ）"
echo "  - $CODEX_HOME/hooks/codex-triage（初回プロンプト分類ラッパー）"
echo ""
echo "Claude Code を再起動するか /reload-skills を実行してください。"
echo "Codex分類を使う場合: $CODEX_HOME/hooks/codex-triage [codex options] -- '<prompt>'"
echo ""
echo "（opt-in）quorum/cadence トリアージの自動判定を有効化するには ~/.claude/settings.json の hooks に追記:"
echo '  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",'
echo "    \"command\": \"$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh\", \"timeout\": 30}]}]}}"
echo "  ※ プロンプトごとに haiku 分類が走る（+2〜6秒・微小コスト）。24字未満と / 始まりはスキップ。"
