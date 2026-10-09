#!/usr/bin/env python3
"""Stopフック: 文章だけで番を終えても「完了」とみなさない（Opus 5.5公式の早止まり対策）。

公式（Prompting Claude Opus 5.5 > Unattended agentic runs）の要点をそのまま機械にしたもの:
- 文章だけの番の終わりは報告であって、完了の証拠ではない
- 作業はチェックリスト（ここでは state.json）で持ち、未完了が残り止まる理由も無ければ、残りを名指しして続けさせる
- バックグラウンドの作業（サブエージェント・コマンド）が走っている間は完了とみなさず、戻りを待つ
- 同じ作業への自動の続行は2〜3回まで。本当に詰まった実行は止めて人が見直せるようにする

効くのは、統括役として起動したセッション（agent_type が pipeline.json の conductor）で、
実行が進行中（state.json の active）の時だけ。人が付き添う時は `loopctl.py pause` で止める
（公式: 人が付き添う対話型の使い方には入れない）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loopctl as lc  # noqa: E402


def nudge_finish(p: dict) -> int:
    """全工程が完了したのに実行が開いたまま止まろうとしている。retroを貼って finish するよう促し、
    促しても閉じなければ自分で閉じる（統括役が閉じず、人が finish する回が続いた。IMPROVEMENTS 2026-09-29）。"""
    limit = p.get("max_auto_continues", 3)
    with lc.locked():
        st = lc.load_json(lc.STATE)
        g = st.setdefault("stop_guard", {"count": 0, "fingerprint": ""})
        if g.get("fingerprint") != "finish":
            g["count"], g["fingerprint"] = 0, "finish"
        if g["count"] >= limit:
            st["active"], st["finished"], st["finished_at"] = False, True, lc.now()
            lc.record_run(st)
            st["stop_guard"] = {"count": 0, "fingerprint": ""}
            lc.save_json(lc.STATE, st)
            print(json.dumps({"systemMessage": "ループ: 全工程が完了したまま閉じられなかったので、実行を閉じました（finish）。"
                              "振り返り（`loopctl.py retro`）が candidates.md に無ければ貼ってください"}, ensure_ascii=False))
            return 0
        g["count"] += 1
        lc.save_json(lc.STATE, st)
    reason = ("全工程が完了しています。実行を閉じてから止まってください: ①`loopctl.py retro`の出力を candidates.md の"
              "「振り返り」節へ貼ってcommit（メッセージに`記録なし: ループの記録のみ`）②`loopctl.py finish`。"
              "報告は finish と同じメッセージか、その後に書いてください。")
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        p = lc.pipeline()
        st = lc.load_json(lc.STATE)
    except Exception:
        return 0
    if not st or not st.get("active"):
        return 0
    # 統括役として起動したセッション（claude --agent loop-conductor）だけで効かせる。
    # 同じリポで人が普通に対話しているセッションには催促しない
    conductor = p.get("conductor", "loop-conductor")
    if conductor and data.get("agent_type") != conductor:
        return 0
    # 走っている作業があれば、その戻りが次の番を起こす。ここで催促すると二重に動く
    if data.get("background_tasks"):
        return 0

    why = lc.limit_reason(st, p)
    if why:
        with lc.locked():
            st = lc.load_json(lc.STATE)
            lc.halt(st, why)
            lc.save_json(lc.STATE, st)
        print(json.dumps({"systemMessage": f"ループ: {why}。実行を止めました（`loopctl.py status`）"}, ensure_ascii=False))
        return 0

    items = lc.open_items(st, p)
    if not items:
        steps = st.get("steps") or {}
        if steps and all(s["status"] == "done" for s in steps.values()):
            return nudge_finish(p)
        return 0  # 残りは人待ち（止まってよい止まり方）

    with lc.locked():
        st = lc.load_json(lc.STATE)
        g = st.setdefault("stop_guard", {"count": 0, "fingerprint": ""})
        fp = lc.fingerprint(st)
        if fp != g.get("fingerprint"):
            g["count"] = 0  # 前回の催促から状態が進んでいれば、数え直す
        limit = p.get("max_auto_continues", 3)
        if g["count"] >= limit:
            g["count"] = 0
            g["fingerprint"] = ""
            st["active"] = False
            st["halted"] = f"自動の続行が{limit}回続いても状態が進まなかったため止めました"
            lc.save_json(lc.STATE, st)
            print(json.dumps({"systemMessage": f"ループ: {st['halted']}。`loopctl.py status` で詰まりを確かめ、`loopctl.py resume` で再開できます"},
                             ensure_ascii=False))
            return 0
        g["count"] += 1
        g["fingerprint"] = fp
        st["nudges_total"] = st.get("nudges_total", 0) + 1  # 振り返り（retro）で数える
        lc.save_json(lc.STATE, st)

    budget = lc.effective_budget(st, p)
    elapsed = int(lc.now() - st["started_at"])
    time_line = f"\nelapsed {elapsed}s / {budget}s" if budget else ""
    reason = (
        "ループの作業表にまだ未完了の項目があります: " + "; ".join(items) + "。"
        "続けてください。止まっている理由があるなら、`loopctl.py block <工程> \"<理由>\"` で書いてから止まってください。"
        "報告は次のツール呼び出しと同じメッセージに書いてください。"
        + time_line
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
