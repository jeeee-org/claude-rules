#!/usr/bin/env bash
# triage-classifier.sh — UserPromptSubmit フック
# ユーザープロンプトを haiku がヘッドレスで T0/T1/T2a/CADENCE に分類し、
# T0 以外のときだけ判定結果をコンテキストに注入する（quorum/cadence トリアージの発動漏れ対策）。
# 設計方針: fail-open（分類に失敗してもプロンプトを絶対に止めない）・T0 は無出力（ノイズゼロ）。
# 登録方法は claude-rules/install.sh の出力を参照。
set -u

# 再帰ガード: 自前の環境変数で「このフックが起動した子」を検出する。
# 子の claude が発火するフックにも env が继承されるため、ここで即 no-op になり再帰しない。
# 注意（2026-07-10 実測・v2.1.206）:
#  - CLAUDE_CODE_CHILD_SESSION はメインセッション自体に立っていることがあり、入口ガード不可。
#  - --bare は認証情報まで読み飛ばし "Not logged in" で失敗するため使わない。
[ -n "${TRIAGE_CLASSIFIER_ACTIVE:-}" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0
command -v claude >/dev/null 2>&1 || exit 0

input=$(cat)
prompt=$(jq -r '.user_input // empty' <<<"$input" 2>/dev/null) || exit 0

# スキップ: 空 / スラッシュコマンド（明示指定が最優先） / 短文（相槌・雑談）
[ -z "$prompt" ] && exit 0
case "$prompt" in "/"*) exit 0 ;; esac
[ "${#prompt}" -lt 24 ] && exit 0

RUBRIC='あなたはトリアージ分類器。次の「ユーザープロンプト」を1行で分類せよ。出力は以下のいずれか1行のみ。説明・前置き・コードブロック禁止。
T0
T1|<理由を15字以内>
T2a|<理由を15字以内>
CADENCE|<フロー名>|<理由を15字以内>

基準:
- T1 = 高ステークス×広さ型。技術選定・障害の根本原因・相場観・事実の争い・見落としが痛い設計/調査の問い。
- T2a = 高ステークス×深さ型。数学・設計の一貫性検証・単一文書の精読。
- CADENCE = 次の3条件を全部満たす作業依頼: ①完成の定義を1文で言える ②途中の人間の関与が承認/却下に還元できる ③被覆型の監査・調査・定型修正。フロー名は audit-reliability / error-analysis / investigate-subsystem / optimize-context / fix-reliability から最も近いもの。
- T0 = それ以外（単純な作業指示・機械的な編集・雑談・軽い質問・相談の途中の相槌）。
- メインモデルは見送り側に偏る前提で、境界例は T0 でなく該当候補側に倒す。'

# 軽量化（2026-07-10 実測・v2.1.206。素の claude -p は約12〜16秒 → 以下で約4〜6秒）:
#  - MAX_THINKING_TOKENS=0: thinking を切る（切らないと1行分類に900+トークン思考して最大の遅延要因になる）
#  - --system-prompt: 既定のフルシステムプロンプト＋CLAUDE.md（約3万トークン）を差し替え
#  - --strict-mcp-config: MCP サーバーを読み込まない（分類にツールは不要）
result=$(TRIAGE_CLASSIFIER_ACTIVE=1 MAX_THINKING_TOKENS=0 CLAUDE_EFFORT=low timeout 20 \
  claude -p --model haiku --strict-mcp-config \
  --system-prompt "あなたは1行分類器。指示された形式の1行のみ出力する。" "$RUBRIC

--- ユーザープロンプト ---
$prompt" 2>/dev/null) || exit 0

# 出力の1行目だけ採用し、想定形式か検証（想定外は無視 = fail-open）
line=$(head -n1 <<<"$result" | tr -d '\r')
case "$line" in
  T0) exit 0 ;;
  T1\|*|T2a\|*|CADENCE\|*) ;;
  *) exit 0 ;;
esac

ctx="自動トリアージ（haiku 分類フック）: ${line} 相当と判定。グローバル CLAUDE.md のトリアージ規則に従い、応答冒頭で宣言し、該当なら /quorum・Fable 単発・/cadence <flow> を1行提案すること。最終判断はメインセッション（この判定は参考情報。ユーザーの明示指定が常に最優先）。"

jq -nc --arg ctx "$ctx" '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$ctx}}'
exit 0
