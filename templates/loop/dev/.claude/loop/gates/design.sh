#!/usr/bin/env bash
# 設計の決定論ゲート。全要件idが設計に現れ、分担とテスト方針の節があるか。
. "$LOOP_DIR/gates/lib.sh"
F=docs/loop/design.md
need_file "$F"
need_all_ids docs/loop/requirements.md "$F" 'REQ-[0-9]+'
need_match "$F" '^## 触ってよいファイル'
need_match "$F" '^## 実装の分担'
need_match "$F" '^## テスト方針'
forbid_match "$F" 'TBD|TODO|要確認'
gate_end
