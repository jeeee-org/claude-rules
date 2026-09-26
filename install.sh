#!/usr/bin/env bash
# claude-rules の道具（スキル・フック・判定スクリプト）をローカルの Claude Code / Codex 設定に配置する。
#   skills/* と hooks/*         -> 各環境の対応ディレクトリ
# **共通ルールそのものはここでは入れない**（2026-09-26にグローバルへの注入を廃止）。共通ルールは
# 各PJの AGENTS.md へ tools/embed-rules.py で書き込む（AIに「このPJにルールを入れて」と頼めば
# install-rules スキルが案内する）。以前の版が $CLAUDE_CONFIG_DIR/CLAUDE.md・$CODEX_HOME/AGENTS.md へ
# 入れたブロックは、ここで取り除く（控えを .bak に取る。PJへの書き込みが済むまで残すなら
# --keep-global-rules）。
#   IMPROVEMENTS.md            -> 各環境の skills/init-rules/ から正本への symlink
# 配置先を変えたい場合:
#   CLAUDE_CONFIG_DIR=/path/.claude CODEX_HOME=/path/.codex ./install.sh
# Codex をメインエージェントに使わないPCでは Codex 側の配置を丸ごと省ける:
#   ./install.sh --no-codex        （または CLAUDE_RULES_INSTALL_CODEX=0 ./install.sh）
#   ※ quorum も AGENTS.md へ注入するため、そちらを止めない限り
#      AGENTS.md 自体は残る。ここで省けるのは claude-rules 分だけ。
# 複数PCへの事前配布を可能にするため、CLI未導入でも両設定ディレクトリを作る。
# 新PCでは claude-rules -> quorum の順に install すると CLAUDE.md の並びが揃う。
# **$CLAUDE_CONFIG_DIR/settings.json を書き換えます**（記録の関門フック2件を hooks へ登録。
# 控えを settings.json.bak に取ります）。登録を止めるなら:
#   ./install.sh --no-hook-register   （または CLAUDE_RULES_REGISTER_HOOKS=0 ./install.sh）
# あわせて表示の設定（settings/display.json。思考の要約・focus表示）を
# **無いキーだけ**足します（PCごとに決めた値は上書きしない）。止めるなら:
#   ./install.sh --no-display-settings （または CLAUDE_RULES_DISPLAY_SETTINGS=0 ./install.sh）
set -euo pipefail

INSTALL_CODEX="${CLAUDE_RULES_INSTALL_CODEX:-1}"
REGISTER_HOOKS="${CLAUDE_RULES_REGISTER_HOOKS:-1}"
DISPLAY_SETTINGS="${CLAUDE_RULES_DISPLAY_SETTINGS:-1}"
KEEP_GLOBAL_RULES=0
for arg in "$@"; do
  case "$arg" in
    --no-codex) INSTALL_CODEX=0 ;;
    --no-hook-register) REGISTER_HOOKS=0 ;;
    --no-display-settings) DISPLAY_SETTINGS=0 ;;
    --keep-global-rules) KEEP_GLOBAL_RULES=1 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "不明な引数: $arg（使えるのは --no-codex / --no-hook-register / --no-display-settings / --keep-global-rules）" >&2; exit 2 ;;
  esac
done
case "$INSTALL_CODEX" in
  0|false|no|'') INSTALL_CODEX=0 ;;
  *) INSTALL_CODEX=1 ;;
esac
case "$REGISTER_HOOKS" in
  0|false|no|'') REGISTER_HOOKS=0 ;;
  *) REGISTER_HOOKS=1 ;;
esac
case "$DISPLAY_SETTINGS" in
  0|false|no|'') DISPLAY_SETTINGS=0 ;;
  *) DISPLAY_SETTINGS=1 ;;
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

TARGET_MD="$CLAUDE_CONFIG_DIR/CLAUDE.md"
CODEX_TARGET_MD="$CODEX_HOME/AGENTS.md"

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

# install-rulesスキル（共通ルールの導入・更新を選択肢で案内する。PJへの書き込みもここから）。
# cloneしただけのPCでも使えるよう、リポの .claude/skills と .agents/skills からも symlink で見せている
rm -rf "$CLAUDE_CONFIG_DIR/skills/install-rules"
cp -R "$SRC_DIR/skills/install-rules" "$CLAUDE_CONFIG_DIR/skills/install-rules"

if [ "$INSTALL_CODEX" = 1 ]; then
  mkdir -p "$CODEX_HOME/skills"
  rm -rf "$CODEX_HOME/skills/install-rules"
  cp -R "$SRC_DIR/skills/install-rules" "$CODEX_HOME/skills/install-rules"
  rm -rf "$CODEX_HOME/skills/init-rules"
  cp -R "$SRC_DIR/skills/init-rules" "$CODEX_HOME/skills/init-rules"   # Claudeと同じ1枚（2026-09-26に一本化）
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

# 記録の関門（commit時にグローバル§3の記録が入っているかを見る）。
#   入口 = PreToolUse。実行前に止められるが、書き込みとcommitが同じ呼び出しだと判定できない
#   後追い = PostToolUse。止められないが、gitの履歴を見るので見逃しが残らない
# あわせてAI帰属行の関門（pushの直前にcommitメッセージを見る。グローバル§5.2 禁止②）も入れる。
# トリアージ分類と違い**既定で有効**にするため、settings.json への登録までここで行う。
# **ユーザーの設定ファイルを書き換えるので、事前に告げ、控えを取り、opt-outを用意する。**
cp "$SRC_DIR/hooks/commit-record-guard.sh" "$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh"
cp "$SRC_DIR/hooks/commit-record-audit.sh" "$CLAUDE_CONFIG_DIR/hooks/commit-record-audit.sh"
cp "$SRC_DIR/hooks/push-record-guard.sh" "$CLAUDE_CONFIG_DIR/hooks/push-record-guard.sh"
cp "$SRC_DIR/hooks/push-attribution-guard.sh" "$CLAUDE_CONFIG_DIR/hooks/push-attribution-guard.sh"
chmod +x "$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh" \
         "$CLAUDE_CONFIG_DIR/hooks/commit-record-audit.sh" \
         "$CLAUDE_CONFIG_DIR/hooks/push-record-guard.sh" \
         "$CLAUDE_CONFIG_DIR/hooks/push-attribution-guard.sh"
GUARD_CMD="$CLAUDE_CONFIG_DIR/hooks/commit-record-guard.sh"
AUDIT_CMD="$CLAUDE_CONFIG_DIR/hooks/commit-record-audit.sh"
PUSH_CMD="$CLAUDE_CONFIG_DIR/hooks/push-record-guard.sh"
ATTR_CMD="$CLAUDE_CONFIG_DIR/hooks/push-attribution-guard.sh"
SETTINGS="$CLAUDE_CONFIG_DIR/settings.json"
GUARD_REGISTERED=0

register_hook() { # register_hook <PreToolUse|PostToolUse> <コマンド>
  local event="$1" cmd="$2"
  if jq -e --arg c "$cmd" --arg e "$event" \
       '[.hooks[$e][]?.hooks[]?.command] | index($c)' "$SETTINGS" >/dev/null 2>&1; then
    return 1   # 登録済み（再installで二重に増やさない）
  fi
  jq --arg c "$cmd" --arg e "$event" '.hooks = (.hooks // {})
     | .hooks[$e] = ((.hooks[$e] // [])
       + [{matcher:"Bash",hooks:[{type:"command",command:$c,timeout:10}]}])' \
     "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  return 0
}

register_record_guard() {
  if [ "$REGISTER_HOOKS" = 0 ]; then
    echo "※ settings.json への登録は省きました（--no-hook-register）。関門は効きません。" >&2
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "※ jqが無いため、記録の関門をsettings.jsonへ登録できませんでした。手で追記してください:" >&2
    echo "   PreToolUse  → $GUARD_CMD" >&2
    echo "   PreToolUse  → $PUSH_CMD" >&2
    echo "   PreToolUse  → $ATTR_CMD" >&2
    echo "   PostToolUse → $AUDIT_CMD" >&2
    echo "   （どちらも matcher は \"Bash\"、timeout 10）" >&2
    return 0
  fi
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
    echo "⚠ $SETTINGS がJSONとして読めません。記録の関門の登録を省きました。" >&2
    return 0
  fi
  local added=0
  if ! jq -e --arg c "$GUARD_CMD" '[.hooks.PreToolUse[]?.hooks[]?.command] | index($c)' \
         "$SETTINGS" >/dev/null 2>&1 ||
     ! jq -e --arg c "$PUSH_CMD" '[.hooks.PreToolUse[]?.hooks[]?.command] | index($c)' \
         "$SETTINGS" >/dev/null 2>&1 ||
     ! jq -e --arg c "$ATTR_CMD" '[.hooks.PreToolUse[]?.hooks[]?.command] | index($c)' \
         "$SETTINGS" >/dev/null 2>&1 ||
     ! jq -e --arg c "$AUDIT_CMD" '[.hooks.PostToolUse[]?.hooks[]?.command] | index($c)' \
         "$SETTINGS" >/dev/null 2>&1; then
    echo "※ 記録の関門を有効にするため、$SETTINGS のhooksへ登録します（控え: $SETTINGS.bak）。"
    echo "   止めるなら: ./install.sh --no-hook-register"
    cp "$SETTINGS" "$SETTINGS.bak"
  fi
  register_hook PreToolUse "$GUARD_CMD" && added=1
  register_hook PreToolUse "$PUSH_CMD" && added=1
  register_hook PreToolUse "$ATTR_CMD" && added=1
  register_hook PostToolUse "$AUDIT_CMD" && added=1
  if [ "$added" = 1 ]; then
    GUARD_REGISTERED=2
    echo "  - settings.jsonに記録の関門とAI帰属行の関門を登録しました（入口・pushの関門2本=PreToolUse、後追い=PostToolUse）"
  else
    GUARD_REGISTERED=1
  fi
}
register_record_guard

# 表示の設定（正本 settings/display.json）。**無いキーだけ足す**——PCごとに選び直した値
# （viewMode等）を再installで戻さないため。to-doツール（CLAUDE_CODE_ENABLE_TODO_TOOLS）は
# 全体には入れず、要るリポの .claude/settings.json で有効にする（README「表示の設定」）。
apply_display_settings() {
  if [ "$DISPLAY_SETTINGS" = 0 ]; then
    echo "※ 表示の設定は省きました（--no-display-settings）。" >&2
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "※ jqが無いため、表示の設定を足せませんでした。settings/display.json を手で $SETTINGS へ写してください" >&2
    return 0
  fi
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
    echo "⚠ $SETTINGS がJSONとして読めません。表示の設定を省きました。" >&2
    return 0
  fi
  local merged added
  merged=$(jq --slurpfile d "$SRC_DIR/settings/display.json" '
    ($d[0]) as $d
    | .env = ((.env // {}) as $e | $e + (($d.env // {}) | with_entries(select(.key as $k | $e | has($k) | not))))
    | reduce ($d | del(.env) | to_entries[]) as $kv (.; if has($kv.key) then . else .[$kv.key] = $kv.value end)
    | if .env == {} then del(.env) else . end' "$SETTINGS") || {
    echo "⚠ 表示の設定を合成できませんでした（jqの失敗）。settings.jsonは変えていません。" >&2; return 0; }
  added=$(jq -rn --argjson a "$(cat "$SETTINGS")" --argjson b "$merged" '
    [($b.env // {} | keys[]) as $k | select(($a.env // {}) | has($k) | not) | "env.\($k)"]
    + [($b | keys[]) as $k | select($k != "env" and ($a | has($k) | not)) | $k] | join(", ")') || added=""
  if [ -n "$added" ]; then
    cp "$SETTINGS" "$SETTINGS.bak"
    printf '%s\n' "$merged" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
    echo "  - settings.jsonに表示の設定を足しました: $added（控え: $SETTINGS.bak。止めるなら --no-display-settings）"
  fi
}
apply_display_settings

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

# 以前の版がグローバルへ入れた共通ルールのブロックを取り除く（2026-09-26に廃止。共通ルールは各PJの
# AGENTS.md にある）。残すとPJ側と二重に読まれる。PJへの書き込みが済む前に外すとルールの無いPJが
# 出るので、移行の途中は --keep-global-rules で残せる
remove_global_block() { # remove_global_block <ファイル> <マーカー名>
  local f="$1" m="$2"
  [ -f "$f" ] && grep -q "$m:begin" "$f" || return 0
  if [ "$KEEP_GLOBAL_RULES" = 1 ]; then
    echo "※ $f に以前の共通ルールのブロックを残しました（--keep-global-rules）。PJと二重に読まれます" >&2
    return 0
  fi
  cp "$f" "$f.bak"
  awk -v m="$m" '$0 ~ m":begin" {skip=1; next} $0 ~ m":end" {skip=0; next} !skip {print}' "$f.bak" |
    awk 'NF {blank=0; print; next} !blank++ {print}' > "$f.tmp" && mv "$f.tmp" "$f"
  echo "  - $f から以前の共通ルールのブロックを取り除きました（控え: $f.bak）"
}
remove_global_block "$TARGET_MD" claude-rules
remove_global_block "$CODEX_TARGET_MD" codex-rules

if [ "$INSTALL_CODEX" != 1 ]; then
  # 既存の配置は**自動で消さない**（env 1つでユーザーのファイルを削るのは危険）。
  # 残っていることと、消す手順だけを知らせる。
  for leftover in "$CODEX_HOME/skills/init-rules" "$CODEX_HOME/skills/triage" \
                  "$CODEX_HOME/hooks/codex-triage" "$CODEX_HOME/tools/check-limits.sh"; do
    if [ -e "$leftover" ]; then
      echo "※ Codex版はスキップしました。前回の配置が残っています: $leftover" >&2
      echo "   不要なら: rm -rf \"$leftover\"" >&2
    fi
  done
fi

# 数値上限の目安チェック（グローバル §2。超過しても失敗にはしない）
echo ""
"$CLAUDE_CONFIG_DIR/tools/check-limits.sh" "$SRC_DIR" || true

echo "✓ インストール完了: $CLAUDE_CONFIG_DIR"
echo "  - skills/init-rules"
echo "  - skills/init-rules/IMPROVEMENTS.md -> $IMPROVEMENTS_FILE (symlink)"
echo "  - skills/migrate-rules（既存PJを記録ルールの改訂へ揃える）"
echo "  - skills/install-rules（共通ルールの導入・更新・PJへの書き込みを案内する）"
echo "  - hooks/triage-classifier.sh（コピーのみ。有効化は下記 opt-in）"
if [ "$GUARD_REGISTERED" = 0 ]; then
  echo "  - hooks/commit-record-guard.sh・commit-record-audit.sh・push-attribution-guard.sh（コピーのみ。登録は上記の案内を参照）"
else
  echo "  - hooks/commit-record-guard.sh（入口の関門。PreToolUse）"
  echo "  - hooks/push-record-guard.sh（**本丸**。pushの関門。PreToolUse）"
  echo "  - hooks/commit-record-audit.sh（見逃しの後追い。PostToolUse）"
  echo "  - hooks/push-attribution-guard.sh（AI帰属行の関門。pushの直前。PreToolUse）"
fi
echo "  - tools/check-limits.sh（常時ロード上限の判定。§2 から参照）"
echo "  - tools/check-record-guard.sh（記録の関門の疎通確認）"
if [ "$INSTALL_CODEX" = 1 ]; then
  echo "  - $CODEX_HOME/skills/init-rules"
  echo "  - $CODEX_HOME/skills/init-rules/IMPROVEMENTS.md -> $IMPROVEMENTS_FILE (symlink)"
  echo "  - $CODEX_HOME/skills/install-rules"
  echo "  - $CODEX_HOME/skills/triage（自然言語での明示トリアージ）"
  echo "  - $CODEX_HOME/hooks/codex-triage（初回プロンプト分類ラッパー）"
else
  echo "  - Codex 側はスキップ（CLAUDE_RULES_INSTALL_CODEX=0 / --no-codex）"
fi
echo ""
echo "記録の関門は三段です: commitの入口（形に弱い）・できたcommitの後追い（止められない）・"
echo "**pushの関門（正確で、止められる）**。記録の無いcommitは、最後にpushで止まります。"
echo "例外はコミットメッセージに「記録なし: <理由>」と書くと通り、理由が履歴に残ります。"
echo "同じpushの直前に、AI帰属行の関門（§5.2 禁止②）も見ます。セッション側から付けよという"
echo "指示が渡っていても規約が勝ちます。例外はCR_SKIP_ATTRIBUTION_GUARD=1のみです。"
echo "効いているかは作業するリポで、**単独の呼び出しで**確かめてください:"
echo "  $CLAUDE_CONFIG_DIR/tools/check-record-guard.sh --repo <リポ>"
echo ""
echo "共通ルールは各PJの AGENTS.md にあります（グローバルには入れません）。PJごとの状態は:"
echo "  python3 $SRC_DIR/tools/embed-rules.py --scan <PJを並べた場所>"
echo "入れる・更新するのはAIに「このPJにルールを入れて」「全PJのルールを最新にして」と頼めば案内されます。"
echo ""
echo "Claude Code を再起動するか /reload-skills を実行してください。"
if [ "$INSTALL_CODEX" = 1 ]; then echo "Codex分類を使う場合: $CODEX_HOME/hooks/codex-triage [codex options] -- '<prompt>'"; fi
echo ""
echo "（opt-in・既定は無効。常時トリアージ規則は 2026-09-15 に廃止）分類フックを使うなら ~/.claude/settings.json の hooks に追記:"
echo '  {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",'
echo "    \"command\": \"$CLAUDE_CONFIG_DIR/hooks/triage-classifier.sh\", \"timeout\": 30}]}]}}"
echo "  ※ プロンプトごとに haiku 分類が走る（+2〜6秒・微小コスト）。24字未満と / 始まりはスキップ。"
