#!/usr/bin/env bash
# Codexには各UserPromptSubmit相当の公開hookがないため、初回プロンプトを分類してからCodexを起動するラッパー。
# Usage: codex-triage [codex options] -- <prompt>
set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUBRIC_FILE="${TRIAGE_RUBRIC_FILE:-$SELF_DIR/triage-rubric.txt}"
MODEL="${CODEX_TRIAGE_MODEL:-gpt-5.4-mini}"
TIMEOUT="${CODEX_TRIAGE_TIMEOUT:-20}"

command -v codex >/dev/null 2>&1 || { echo "codex が見つかりません" >&2; exit 127; }

args=()
prompt_parts=()
separator=0
for arg in "$@"; do
  if [ "$separator" -eq 0 ] && [ "$arg" = "--" ]; then
    separator=1
  elif [ "$separator" -eq 0 ]; then
    args+=("$arg")
  else
    prompt_parts+=("$arg")
  fi
done

# プロンプト無し、短文、明示コマンドは分類せず通常起動。
if [ "${#prompt_parts[@]}" -eq 0 ]; then exec codex "${args[@]}"; fi
prompt="${prompt_parts[*]}"
case "$prompt" in /*) exec codex "${args[@]}" "$prompt" ;; esac
if [ "${#prompt}" -lt 24 ] || [ ! -r "$RUBRIC_FILE" ]; then
  exec codex "${args[@]}" "$prompt"
fi

tmp="$(mktemp)" || exec codex "${args[@]}" "$prompt"
trap 'rm -f "$tmp"' EXIT HUP INT TERM

# --ignore-user-config により子Codexではhooks/AGENTS/追加設定を読まず、再帰を防ぐ。
if timeout "$TIMEOUT" codex -a never -s read-only -m "$MODEL" exec \
  --ephemeral --ignore-user-config --skip-git-repo-check -o "$tmp" \
  "$(cat "$RUBRIC_FILE")

--- ユーザープロンプト ---
$prompt" </dev/null >/dev/null 2>&1; then
  line="$(head -n1 "$tmp" | tr -d '\r')"
else
  line=""
fi

case "$line" in
  T0) rm -f "$tmp"; trap - EXIT; exec codex "${args[@]}" "$prompt" ;;
  T1\|*|T2a\|*|CADENCE\|*)
    context="自動トリアージ（Codex分類ラッパー）: $line 相当と判定。分類の意味は T1=高ステークス×広さ型（並列・多角レビュー）、T2a=高ステークス×深さ型（単独の深い検証）、CADENCE=完成条件が明確な被覆型監査・調査・定型修正。これは参考情報であり、ユーザーの明示指定を常に優先する。Codex版 quorum/cadence が利用可能なら該当フローを提案する。"
    rm -f "$tmp"
    trap - EXIT
    exec codex "${args[@]}" "$context

--- ユーザープロンプト ---
$prompt"
    ;;
  *) rm -f "$tmp"; trap - EXIT; exec codex "${args[@]}" "$prompt" ;;
esac
