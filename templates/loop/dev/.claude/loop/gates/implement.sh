#!/usr/bin/env bash
# 実装の決定論ゲート。変更が設計の範囲内か、ビルド・型・リント・既存テストが通るか。コマンドは commands.env で埋める。
. "$LOOP_DIR/gates/lib.sh"
need_scope docs/loop/design.md "触ってよいファイル"
need_cmd "ビルド" "${BUILD_CMD:-}"
[ -n "${TYPE_CMD:-}" ] && need_cmd "型検査" "$TYPE_CMD"
need_cmd "リント" "${LINT_CMD:-}"
need_cmd "テスト" "${TEST_CMD:-}"
# 例: 衝突マーカー・デバッグ出力の残りを禁止する（リポに合わせて足し引きする）
check_key "衝突マーカー"
if git grep -nE '^(<<<<<<<|>>>>>>>)' -- . >/dev/null 2>&1; then ng "衝突マーカーが残っている"; else ok "衝突マーカーは無い"; fi
gate_end
