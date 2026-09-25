# 決定論ゲートの共通部品。各ゲートの先頭で `. "$LOOP_DIR/gates/lib.sh"` する。
# ゲートの約束: 終了コード0＝合格、それ以外＝不合格。最後の1行が差し戻しの理由として工程役へ渡る。
# 判断の要ることは書かない（それは pipeline.json の judge_questions へ）。
set -u
cd "${REPO_ROOT:?}"
[ -f "$LOOP_DIR/gates/commands.env" ] && . "$LOOP_DIR/gates/commands.env"
GATE_FAILED=0

ok()   { echo "  ✔ $*"; }
ng()   { echo "  ✖ $*"; GATE_FAILED=1; }

# ファイルがあり、空でない
need_file() { if [ -s "$1" ]; then ok "$1 がある"; else ng "$1 が無いか空"; fi; }

# ファイルに正規表現が1つ以上ある / 1つも無い
need_match()   { if grep -Eq -- "$2" "$1" 2>/dev/null; then ok "$1 に /$2/ がある"; else ng "$1 に /$2/ が無い"; fi; }
forbid_match() { if grep -Eqn -- "$2" "$1" 2>/dev/null; then ng "$1 に禁止パターン /$2/ がある: $(grep -En -- "$2" "$1" | head -3 | tr '\n' ' ')"; else ok "$1 に /$2/ は無い"; fi; }

# 元ファイルに出るid（例 REQ-01）が、先ファイルにすべて出る
need_all_ids() {
  local src="$1" dst="$2" re="$3" missing
  missing=$(grep -Eo -- "$re" "$src" 2>/dev/null | sort -u | while read -r id; do grep -Fq -- "$id" "$dst" 2>/dev/null || echo "$id"; done | tr '\n' ' ')
  if [ -z "$missing" ]; then ok "$src のidが $dst にすべてある"; else ng "$dst に無いid: $missing"; fi
}

# コマンドを回して終了コードで判定する。コマンドが未設定なら不合格（黙って通さない）
need_cmd() {
  local label="$1" cmd="${2:-}"
  if [ -z "$cmd" ]; then ng "$label のコマンドが未設定（.claude/loop/gates/commands.env）"; return; fi
  local out; out=$(bash -c "$cmd" 2>&1); local rc=$?
  if [ $rc -eq 0 ]; then ok "$label: $cmd"; else echo "$out" | tail -30; ng "$label が失敗（exit $rc）: $cmd"; fi
}

# pipeline.json のこの工程の outputs（成果物のパス一覧）
step_outputs() {
  python3 - "$LOOP_DIR/pipeline.json" "${LOOP_STEP:?}" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
for s in p["steps"]:
    if s["id"] == sys.argv[2]:
        print("\n".join(s.get("outputs", [])))
PY
}

gate_end() {
  if [ "$GATE_FAILED" -eq 0 ]; then echo "ゲート合格: ${LOOP_STEP}"; exit 0; fi
  echo "ゲート不合格: ${LOOP_STEP}（✖の項目を直してください）"; exit 1
}
