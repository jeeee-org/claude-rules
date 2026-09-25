#!/usr/bin/env bash
# 汎用の決定論ゲート。pipeline.json の outputs に挙げた成果物が揃い、書きかけの印が無いか。
# 工程ごとに別のゲートが要るなら、このファイルを写して pipeline.json の gate を差し替える。
. "$LOOP_DIR/gates/lib.sh"
outs=$(step_outputs)
[ -z "$outs" ] && ng "pipeline.json の outputs が空（何を成果物とするかを書く）"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  need_file "$f"
  forbid_match "$f" 'TBD|TODO|要確認|ここに書く'
done <<<"$outs"
gate_end
