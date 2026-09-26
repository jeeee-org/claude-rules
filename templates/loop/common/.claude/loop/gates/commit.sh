#!/usr/bin/env bash
# コミットの工程のゲート。変更が残らずコミットされたか（と、PJがpushまでを1作業とするならpush済みか）。
# 工程役への指示には「記録（checkpoint等）を書く呼び出しと、git add / commit の呼び出しを分ける」を入れる
# （記録の関門のフックは、書き込みとcommitが同じ呼び出しだと止める）。pushするかは commands.env の PUSH_REQUIRED。
. "$LOOP_DIR/gates/lib.sh"
need_clean_tree
if [ "${PUSH_REQUIRED:-}" = 1 ]; then need_pushed; fi
gate_end
