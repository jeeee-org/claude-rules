#!/usr/bin/env python3
"""SubagentStopフック: ループの工程役・レビュー役・判断役が、決まった形の報告なしに終わるのを1回だけ差し戻す。

狙いは2つ。
1. 「次は○○します」と書いて終わる早止まりを、サブエージェントでも捕まえる
2. 何をしたかが統括役（と人）に必ず届くようにする（サブエージェントの様子が分からない問題）

最後のメッセージに、行頭が `STATUS: done|blocked|partial` の行が無ければ差し戻す。
判断役（gate-judge）は `"answers"` を含むJSONを返していれば通す。
差し戻しは1回だけ（stop_hook_active が立っていれば通す）。無限の押し問答にしない。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loopctl as lc  # noqa: E402

STATUS_RE = re.compile(r"^\s*STATUS:\s*(done|blocked|partial)\b", re.M)


def loop_agents(p: dict) -> set[str]:
    names = {p.get("judge", {}).get("agent", "gate-judge")}
    for s in p.get("steps", []):
        for k in ("worker", "reviewer"):
            if s.get(k):
                names.add(s[k])
    return names


def main() -> int:
    try:
        data = json.load(sys.stdin)
        p = lc.pipeline()
    except Exception:
        return 0
    agent = data.get("agent_type") or ""
    if agent not in loop_agents(p) or data.get("stop_hook_active"):
        return 0
    msg = data.get("last_assistant_message") or ""
    if agent == p.get("judge", {}).get("agent", "gate-judge"):
        if '"answers"' in msg:
            return 0
        reason = '回答を `{"answers": [{"id": ..., "answer": ..., "confidence": 0.0〜1.0, "reason": ...}]}` のJSONだけで返してください。'
    else:
        if STATUS_RE.search(msg):
            return 0
        reason = ("終える前に、決まった形の報告を最後に書いてください。"
                  "1行目は `STATUS: done`（やり終えた）・`STATUS: blocked`（先へ進めない。理由を書く）・`STATUS: partial`（途中。残りを書く）のどれか。"
                  "続けて「やったこと」「成果物（パス）」「確かめたこと（実行したコマンドと結果）」「残り・懸念」。"
                  "まだやれる作業が残っているなら、報告より先にその作業を続けてください。")
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
