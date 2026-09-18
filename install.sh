#!/usr/bin/env bash
# claude-rules をローカルの Claude Code / Codex 設定に配置する。
#   rules/global-rules.md       -> $CLAUDE_CONFIG_DIR/CLAUDE.md
#   rules/codex-global-rules.md -> $CODEX_HOME/AGENTS.md
#   skills/* と hooks/*         -> 各環境の対応ディレクトリ
#   IMPROVEMENTS.md            -> 各環境の skills/init-rules/ から正本への symlink
# 配置先を変えたい場合:
#   CLAUDE_CONFIG_DIR=/path/.claude CODEX_HOME=/path/.codex ./install.sh
# Codex をメインエージェントに使わないPCでは Codex 側の配置を丸ごと省ける:
#   ./install.sh --no-codex        （または CLAUDE_RULES_INSTALL_CODEX=0 ./install.sh）
#   ※ quorum も AGENTS.md へ注入するため、そちらを止めない限り
#      AGENTS.md 自体は残る。ここで省けるのは claude-rules 分だけ。
# 複数PCへの事前配布を可能にするため、CLI未導入でも両設定ディレクトリを作る。
# 新PCでは claude-rules -> quorum の順に install すると CLAUDE.md の並びが揃う。
set -euo pipefail

INSTALL_CODEX="${CLAUDE_RULES_INSTALL_CODEX:-1}"
for arg in "$@"; do
  case "$arg" in
    --no-codex) INSTALL_CODEX=0 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "不明な引数: $arg（使えるのは --no-codex）" >&2; exit 2 ;;
  esac
done
case "$INSTALL_CODEX" in
  0|false|no|'') INSTALL_CODEX=0 ;;
  *) INSTALL_CODEX=1 ;;
esac

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

IMPROVEMENTS_FILE="$SRC_DIR/IMPROVEMENTS.md"

# install 先の symlink は $SRC_DIR への**絶対パス**を焼き込む。リポを移動して再 install を
# 忘れると全ホストのリンクが同時に dangling になり、IMPROVEMENTS.md は実行時の追記が
# 正本へ届かないまま黙って落ちる（cadence で実発生。cadence IMPROVEMENTS 2026-08-27）。
# 張り直す前に「別パスを指していた / 切れていた」ことを知らせる。
warn_stale_link() { # warn_stale_link <リンクのパス> <あるべき実体> <用途の説明>
  local link="$1" want="$2" what="$3" old
  [ -L "$link" ] || return 0
  old="$(readlink "$link")"
  [ "$old" = "$want" ] && return 0
  echo "⚠ 既存の $what リンクが別の場所を指していました: $link -> $old" >&2
  if [ ! -e "$link" ]; then
    echo "   リンク切れです（$old が存在しない）。前回 install 以降にリポを移動した可能性があります。" >&2
    echo "   この間に書かれた改善メモは正本へ届いていません。旧パスが残っていれば追記分を回収してください。" >&2
  fi
  echo "   今回の install で $want へ張り直します。" >&2
}

# 張り直したリンクが実際に解決することを確認する（黙って壊れたまま配置しない）。
verify_link() { # verify_link <リンクのパス> <用途の説明>
  local link="$1" what="$2"
  [ -e "$link" ] && return 0
  echo "✗ $what のリンクが解決できません: $link -> $(readlink "$link")" >&2
  exit 1
}

# ここが claude-rules の clone 自身かどうか。配布先へ取り込まれた複製（他リポの
# bundled/ 配下など）では rules/*.md は pull 専用で、そこでの編集は上流へ届かず
# 次の取り込みで黙って消える。生成物側はマーカー行で止めているが、複製された
# 正本側には歯止めが無く、実際に編集して install まで通してしまった（IMPROVEMENTS
# 2026-09-01）。止めはしないが、気づけるように必ず知らせる。
warn_if_not_upstream_clone() {
  local top
  top="$(git -C "$SRC_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$top" ] && [ "$(cd "$top" && pwd -P)" = "$(cd "$SRC_DIR" && pwd -P)" ] &&
     git -C "$SRC_DIR" remote get-url origin 2>/dev/null | grep -q 'claude-rules'; then
    return 0
  fi
  echo "※ ここは claude-rules の clone ではありません（配布先へ取り込まれた複製）。" >&2
  echo "   rules/*.md はこのPCでは pull 専用です。ここでの編集は上流へ届かず、次の取り込みで消えます。" >&2
  echo "   気づきは IMPROVEMENTS.md へ書き足し、ルール本体は正本のPCで直してください。" >&2
  if [ -n "$(git -C "$SRC_DIR" status --porcelain -- rules 2>/dev/null)" ]; then
    echo "⚠ しかも rules/ に未コミットの変更があります。今回の install はその内容を配置します。" >&2
  fi
}
warn_if_not_upstream_clone

RULES_FILE="$SRC_DIR/rules/global-rules.md"
TARGET_MD="$CLAUDE_CONFIG_DIR/CLAUDE.md"
CODEX_RULES_FILE="$SRC_DIR/rules/codex-global-rules.md"
CODEX_TARGET_MD="$CODEX_HOME/AGENTS.md"

# 正本の自己検証（マーカー欠落のまま配ると注入が壊れる）
grep -q 'claude-rules:begin' "$RULES_FILE" && grep -q 'claude-rules:end' "$RULES_FILE" || {
  echo "✗ rules/global-rules.md にマーカーがありません。修正してから再実行してください。" >&2
  exit 1
}
if [ "$INSTALL_CODEX" = 1 ]; then
  grep -q 'codex-rules:begin' "$CODEX_RULES_FILE" && grep -q 'codex-rules:end' "$CODEX_RULES_FILE" || {
    echo "✗ rules/codex-global-rules.md にマーカーがありません。" >&2
    exit 1
  }
fi

[ -f "$IMPROVEMENTS_FILE" ] || {
  echo "✗ IMPROVEMENTS.md がありません（symlink 先の正本）。" >&2
  exit 1
}

warn_stale_link "$CLAUDE_CONFIG_DIR/skills/init-rules/IMPROVEMENTS.md" "$IMPROVEMENTS_FILE" "IMPROVEMENTS.md"
if [ "$INSTALL_CODEX" = 1 ]; then
  warn_stale_link "$CODEX_HOME/skills/init-rules/IMPROVEMENTS.md" "$IMPROVEMENTS_FILE" "IMPROVEMENTS.md"
fi

mkdir -p "$CLAUDE_CONFIG_DIR/skills"

# init-rules スキルをコピー（正本はリポ側）
rm -rf "$CLAUDE_CONFIG_DIR/skills/init-rules"
cp -R "$SRC_DIR/skills/init-rules" "$CLAUDE_CONFIG_DIR/skills/init-rules"
# IMPROVEMENTS.md はリポ root を正本にし、install 先は symlink。実行時の追記が
# git 管理下のリポ側へ書き込まれ、再インストールの rm -rf でも消えない。
ln -sfn "$IMPROVEMENTS_FILE" "$CLAUDE_CONFIG_DIR/skills/init-rules/IMPROVEMENTS.md"
verify_link "$CLAUDE_CONFIG_DIR/skills/init-rules/IMPROVEMENTS.md" "IMPROVEMENTS.md"

# migrate-rulesスキル（既存PJを記録ルールの改訂へ揃える）。使うコマンドは配置せず、
# init-rulesのIMPROVEMENTS.mdのsymlinkからcloneの場所を辿って呼ぶ
rm -rf "$CLAUDE_CONFIG_DIR/skills/migrate-rules"
cp -R "$SRC_DIR/skills/migrate-rules" "$CLAUDE_CONFIG_DIR/skills/migrate-rules"

if [ "$INSTALL_CODEX" = 1 ]; then
  mkdir -p "$CODEX_HOME/skills"
  rm -rf "$CODEX_HOME/skills/init-rules"
  cp -R "$SRC_DIR/skills/codex-init-rules" "$CODEX_HOME/skills/init-rules"
  ln -sfn "$IMPROVEMENTS_FILE" "$CODEX_HOME/skills/init-rules/IMPROVEMENTS.md"
  verify_link "$CODEX_HOME/skills/init-rules/IMPROVEMENTS.md" "IMPROVEMENTS.md"
  rm -rf "$CODEX_HOME/skills/triage"
  cp -R "$SRC_DIR/skills/codex-triage" "$CODEX_HOME/skills/triage"
fi

# トリアージ分類フックをコピー（settings.json への登録は opt-in。末尾の案内参照）
mkdir -p "$CLAUDE_CONFIG_DIR/hooks"
cp "$SRC_DIR/hooks/triage-classifier.sh" "$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh"
cp "$SRC_DIR/hooks/triage-rubric.txt" "$CLAUDE_CONFIG_DIR/hooks/triage-rubric.txt"
chmod +x "$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh"

# 記録の関門フック（commit時にグローバル§3の記録が入っているかを見る）。
# トリアージ分類と違い**既定で有効**にするので、settings.json への登録までここで行う。
# ユーザーのファイルを書き換えるので、控えを取り、読めない時は何もせず知らせる。
cp "$SRC_DIR/hooks/commit-record-guard.sh" "$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh"
chmod +x "$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh"
GUARD_CMD="$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh"
SETTINGS="$CLAUDE_CONFIG_DIR/settings.json"
GUARD_REGISTERED=0
register_record_guard() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "※ jqが無いため、記録の関門をsettings.jsonへ登録できませんでした。手で追記してください:" >&2
    echo "   {\"hooks\":{\"PreToolUse\":[{\"matcher\":\"Bash\",\"hooks\":[{\"type\":\"command\",\"command\":\"$GUARD_CMD\",\"timeout\":10}]}]}}" >&2
    return 0
  fi
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
    echo "⚠ $SETTINGS がJSONとして読めません。記録の関門の登録を省きました。" >&2
    return 0
  fi
  if jq -e --arg c "$GUARD_CMD" '[.hooks.PreToolUse[]?.hooks[]?.command] | index($c)' \
       "$SETTINGS" >/dev/null 2>&1; then
    GUARD_REGISTERED=1   # 登録済み（再installで二重に増やさない）
    return 0
  fi
  cp "$SETTINGS" "$SETTINGS.bak"
  jq --arg c "$GUARD_CMD" '.hooks = (.hooks // {})
     | .hooks.PreToolUse = ((.hooks.PreToolUse // [])
       + [{matcher:"Bash",hooks:[{type:"command",command:$c,timeout:10}]}])' \
     "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  GUARD_REGISTERED=2
  echo "  - settings.jsonに記録の関門を登録しました（控え: $SETTINGS.bak）"
}
register_record_guard

if [ "$INSTALL_CODEX" = 1 ]; then
  mkdir -p "$CODEX_HOME/hooks"
  cp "$SRC_DIR/hooks/codex-triage.sh" "$CODEX_HOME/hooks/codex-triage"
  cp "$SRC_DIR/hooks/triage-rubric.txt" "$CODEX_HOME/hooks/triage-rubric.txt"
  chmod +x "$CODEX_HOME/hooks/codex-triage"
fi

# 上限判定スクリプト（グローバル §2 から参照される）
mkdir -p "$CLAUDE_CONFIG_DIR/tools"
cp "$SRC_DIR/tools/check-limits.sh" "$CLAUDE_CONFIG_DIR/tools/check-limits.sh"
chmod +x "$CLAUDE_CONFIG_DIR/tools/check-limits.sh"
# 記録の関門の疎通確認（登録しても発火しないセッションが実在するため、導入の一部として回す）
cp "$SRC_DIR/tools/check-record-guard.sh" "$CLAUDE_CONFIG_DIR/tools/check-record-guard.sh"
chmod +x "$CLAUDE_CONFIG_DIR/tools/check-record-guard.sh"
if [ "$INSTALL_CODEX" = 1 ]; then
  mkdir -p "$CODEX_HOME/tools"
  cp "$SRC_DIR/tools/check-limits.sh" "$CODEX_HOME/tools/check-limits.sh"
  chmod +x "$CODEX_HOME/tools/check-limits.sh"
fi

# グローバル CLAUDE.md に claude-rules ブロックを注入する
# （マーカー間を置換、無ければ末尾に追記。quorum-triage と同方式）
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

if [ "$INSTALL_CODEX" = 1 ]; then
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
else
  # 既存の配置は**自動で消さない**（env 1つでユーザーのファイルを削るのは危険）。
  # 残っていることと、消す手順だけを知らせる。
  for leftover in "$CODEX_HOME/skills/init-rules" "$CODEX_HOME/skills/triage" \
                  "$CODEX_HOME/hooks/codex-triage" "$CODEX_HOME/tools/check-limits.sh"; do
    if [ -e "$leftover" ]; then
      echo "※ Codex版はスキップしました。前回の配置が残っています: $leftover" >&2
      echo "   不要なら: rm -rf \"$leftover\"" >&2
    fi
  done
  if [ -f "$CODEX_TARGET_MD" ] && grep -q 'codex-rules:begin' "$CODEX_TARGET_MD"; then
    echo "※ $CODEX_TARGET_MD に codex-rules ブロックが残っています（マーカー間を手で削除してください）" >&2
  fi
fi

# 数値上限の目安チェック（グローバル §2。超過しても失敗にはしない）
echo ""
"$CLAUDE_CONFIG_DIR/tools/check-limits.sh" "$SRC_DIR" || true

echo "✓ インストール完了: $CLAUDE_CONFIG_DIR"
echo "  - CLAUDE.md（claude-rules ブロック）"
echo "  - skills/init-rules"
echo "  - skills/init-rules/IMPROVEMENTS.md -> $IMPROVEMENTS_FILE (symlink)"
echo "  - skills/migrate-rules（既存PJを記録ルールの改訂へ揃える）"
echo "  - hooks/triage-classifier.sh（コピーのみ。有効化は下記 opt-in）"
if [ "$GUARD_REGISTERED" = 0 ]; then
  echo "  - hooks/commit-record-guard.sh（コピーのみ。登録は上記の案内を参照）"
else
  echo "  - hooks/commit-record-guard.sh（commit時の記録の関門。既定で有効）"
fi
echo "  - tools/check-limits.sh（常時ロード上限の判定。§2 から参照）"
echo "  - tools/check-record-guard.sh（記録の関門の疎通確認）"
if [ "$INSTALL_CODEX" = 1 ]; then
  echo "  - $CODEX_TARGET_MD（codex-rules ブロック）"
  echo "  - $CODEX_HOME/skills/init-rules"
  echo "  - $CODEX_HOME/skills/init-rules/IMPROVEMENTS.md -> $IMPROVEMENTS_FILE (symlink)"
  echo "  - $CODEX_HOME/skills/triage（自然言語での明示トリアージ）"
  echo "  - $CODEX_HOME/hooks/codex-triage（初回プロンプト分類ラッパー）"
else
  echo "  - Codex 側はスキップ（CLAUDE_RULES_INSTALL_CODEX=0 / --no-codex）"
fi
echo ""
echo "記録の関門は、登録しても発火するとは限りません（**リポ単位で割れる例**があり、条件は未特定）。"
echo "**作業するリポで**確かめてください: $CLAUDE_CONFIG_DIR/tools/check-record-guard.sh --repo <リポ>"
echo ""
echo "Claude Code を再起動するか /reload-skills を実行してください。"
if [ "$INSTALL_CODEX" = 1 ]; then echo "Codex分類を使う場合: $CODEX_HOME/hooks/codex-triage [codex options] -- '<prompt>'"; fi
echo ""
echo "（opt-in・既定は無効。常時トリアージ規則は 2026-09-15 に廃止）分類フックを使うなら ~/.claude/settings.json の hooks に追記:"
echo '  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",'
echo "    \"command\": \"$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh\", \"timeout\": 30}]}]}}"
echo "  ※ プロンプトごとに haiku 分類が走る（+2〜6秒・微小コスト）。24字未満と / 始まりはスキップ。"
