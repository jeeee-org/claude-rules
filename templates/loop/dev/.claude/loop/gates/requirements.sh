#!/usr/bin/env bash
# 要件の決定論ゲート。形が整っているかだけを機械で見る（中身の妥当さはレビュー役と判断役）。
. "$LOOP_DIR/gates/lib.sh"
F=docs/loop/requirements.md
need_file "$F"
need_match "$F" 'REQ-[0-9]+'
need_match "$F" '受け入れ条件'
forbid_match "$F" 'TBD|TODO|要確認|\?\?\?'
gate_end
