#!/usr/bin/env bash
# 常時ロードされるファイルのサイズ上限を機械判定する（グローバル §2）。
#   check-limits.sh [PJルート]     省略時はカレントディレクトリ
# 上限は 1024 系。PJ ごとに環境変数で上書きできる:
#   CR_LIMIT_GLOBAL=14336 CR_LIMIT_PJ=6144 CR_LIMIT_PROGRESS_BYTES=12288 CR_LIMIT_PROGRESS_LINES=60
# 超過が1件でもあれば exit 1。
set -uo pipefail

PJ="${1:-$PWD}"
CC="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CX="${CODEX_HOME:-$HOME/.codex}"
G="${CR_LIMIT_GLOBAL:-14336}"
P="${CR_LIMIT_PJ:-6144}"
PB="${CR_LIMIT_PROGRESS_BYTES:-12288}"
PL="${CR_LIMIT_PROGRESS_LINES:-60}"
NG=0

chk() { # ラベル ファイル 上限 単位
  local label="$1" f="$2" lim="$3" unit="$4" val
  [ -f "$f" ] || return 0
  if [ "$unit" = 行 ]; then val=$(wc -l < "$f"); else val=$(wc -c < "$f"); fi
  val=$((val))
  if [ "$val" -gt "$lim" ]; then
    printf '⚠ %-26s %7d%s / %d%s  (%+d)\n' "$label" "$val" "$unit" "$lim" "$unit" "$((val-lim))"
    NG=1
  else
    printf '✓ %-26s %7d%s / %d%s\n' "$label" "$val" "$unit" "$lim" "$unit"
  fi
}

echo "— グローバル（全セッションでロード）"
chk "${CC/#$HOME/\~}/CLAUDE.md" "$CC/CLAUDE.md" "$G" B
chk "${CX/#$HOME/\~}/AGENTS.md" "$CX/AGENTS.md" "$G" B

echo "— PJ: ${PJ/#$HOME/\~}"
chk "CLAUDE.md"   "$PJ/CLAUDE.md"   "$P"  B
chk "AGENTS.md"   "$PJ/AGENTS.md"   "$P"  B
chk "PROGRESS.md" "$PJ/PROGRESS.md" "$PB" B
chk "PROGRESS.md (行数)" "$PJ/PROGRESS.md" "$PL" 行

[ "$NG" -eq 0 ] || echo "→ 超過あり。/cadence optimize-context 等で \"cut bytes, not meaning\"。"
exit "$NG"
