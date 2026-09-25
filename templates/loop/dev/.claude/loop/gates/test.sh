#!/usr/bin/env bash
# テストの決定論ゲート。全テストが通り、全要件idがテスト報告に載っているか。
. "$LOOP_DIR/gates/lib.sh"
need_cmd "テスト" "${TEST_CMD:-}"
need_file docs/loop/test-report.md
need_all_ids docs/loop/requirements.md docs/loop/test-report.md 'REQ-[0-9]+'
forbid_match docs/loop/test-report.md '失敗|FAIL|未実施'
gate_end
