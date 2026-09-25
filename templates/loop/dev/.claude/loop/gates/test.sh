#!/usr/bin/env bash
# テストの決定論ゲート。全テストが通り、全要件idがテスト報告の表に載り、結果がすべて合格か。
. "$LOOP_DIR/gates/lib.sh"
need_cmd "テスト" "${TEST_CMD:-}"
need_file docs/loop/test-report.md
# 表の結果列（最後の列）で判定する。語の有無では判定しない
need_table_pass docs/loop/requirements.md docs/loop/test-report.md 'REQ-[0-9]+'
gate_end
