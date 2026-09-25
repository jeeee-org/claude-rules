#!/usr/bin/env python3
"""ループの状態を機械で動かす道具（claude-rulesのループひな型）。

統括役（loop-conductor）もサブエージェントも、工程の状態は**必ずこれを通して**変える。
状態の遷移・順序の強制・決定論ゲートの実行・判断役の回答への閾値の当てはめ・
学習用の記録は、すべてここで行う（モデルの自己申告に任せない）。

置き場: <repo>/.claude/loop/bin/loopctl.py   設定: <repo>/.claude/loop/pipeline.json
状態:   <repo>/.claude/loop/state.json（実行ごと・git管理外）
記録:   <repo>/.claude/loop/judge/judgments.jsonl（学習用・git管理する）
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules as rl  # noqa: E402

LOOP_DIR = Path(os.environ.get("LOOP_DIR") or Path(__file__).resolve().parent.parent)
PIPELINE = LOOP_DIR / "pipeline.json"
STATE = LOOP_DIR / "state.json"
JUDGE_DIR = LOOP_DIR / "judge"
JUDGMENTS = JUDGE_DIR / "judgments.jsonl"
CALIBRATION = JUDGE_DIR / "calibration.json"
LESSONS = JUDGE_DIR / "lessons.md"
RULES = JUDGE_DIR / "rules.json"
REPO = LOOP_DIR.parent.parent
LOCK = LOOP_DIR / ".state.lock"

OPEN = ("pending", "in_progress", "review", "gate", "judge")
LABEL = {
    "pending": "未着手",
    "in_progress": "作業中",
    "review": "レビュー待ち",
    "gate": "ゲート待ち",
    "judge": "判断待ち",
    "done": "完了",
    "blocked": "止まっている",
}


class LoopError(Exception):
    pass


# ---------- 読み書き ----------

def now() -> float:
    return float(os.environ.get("LOOP_NOW") or time.time())


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


@contextlib.contextmanager
def locked():
    """並列のサブエージェントが同時に書いても壊れないよう、状態の更新を直列にする。"""
    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def pipeline() -> dict:
    p = load_json(PIPELINE)
    if p is None:
        raise LoopError(f"{PIPELINE} がありません")
    ids = [s["id"] for s in p.get("steps", [])]
    if len(ids) != len(set(ids)):
        raise LoopError("pipeline.json の工程idが重複しています")
    return p


def step_def(p: dict, sid: str) -> dict:
    for s in p["steps"]:
        if s["id"] == sid:
            return s
    raise LoopError(f"工程 {sid} は pipeline.json にありません（あるのは {', '.join(x['id'] for x in p['steps'])}）")


def after_of(p: dict, sid: str) -> list[str]:
    """先に終わっているべき工程。書かなければ直前の工程1つ。"""
    s = step_def(p, sid)
    if "after" in s:
        return list(s["after"])
    ids = [x["id"] for x in p["steps"]]
    i = ids.index(sid)
    return [ids[i - 1]] if i > 0 else []


def state() -> dict:
    st = load_json(STATE)
    if st is None:
        raise LoopError("実行が始まっていません。先に `loopctl.py begin` を実行してください")
    return st


def st_step(st: dict, sid: str) -> dict:
    if sid not in st["steps"]:
        raise LoopError(f"工程 {sid} は今回の実行にありません")
    return st["steps"][sid]


def note(stp: dict, text: str) -> None:
    stp.setdefault("notes", []).append({"t": now(), "text": text})
    stp["notes"] = stp["notes"][-20:]


# ---------- 集計（Stopフックからも使う） ----------

def waiting_on_blocked(st: dict, p: dict | None, sid: str, seen=None) -> str | None:
    """この工程の前提（間接も含む）に止まっている工程があれば、その工程id。"""
    if p is None:
        return None
    seen = seen or set()
    for d in after_of(p, sid):
        if d in seen or d not in st["steps"]:
            continue
        seen.add(d)
        if st["steps"][d]["status"] == "blocked":
            return d
        hit = waiting_on_blocked(st, p, d, seen)
        if hit:
            return hit
    return None


def open_items(st: dict, p: dict | None = None) -> list[str]:
    """まだ手を動かせる未完了項目。止まっている工程（人待ち）と、その後ろで待つだけの工程は含めない。"""
    items = []
    for sid, s in st["steps"].items():
        if s["status"] == "pending" and waiting_on_blocked(st, p, sid):
            continue
        if s["status"] in OPEN:
            shards = [k for k, v in s.get("shards", {}).items() if v != "submitted"]
            extra = f"（担当中: {', '.join(shards)}）" if shards and s["status"] == "in_progress" else ""
            items.append(f"{sid}: {LABEL[s['status']]}{extra}")
    return items


def blocked_items(st: dict) -> list[str]:
    return [f"{sid}: {s.get('blocker') or '理由未記入'}" for sid, s in st["steps"].items() if s["status"] == "blocked"]


def fingerprint(st: dict) -> str:
    core = {k: (v["status"], sorted(v.get("shards", {}).items()), v.get("rework", 0)) for k, v in st["steps"].items()}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def render(st: dict, p: dict) -> str:
    lines = [f"実行 {st['run_id']}  状態: {'完了（閉じた）' if st.get('finished') else '進行中' if st['active'] else '一時停止中'}"]
    if st.get("halted"):
        lines.append(f"※ {st['halted']}（`resume`で再開）")
    el = int(now() - st["started_at"])
    budget = p.get("time_budget_sec")
    lines.append(f"経過 {el}s" + (f" / 予算 {budget}s" if budget else ""))
    for sd in p["steps"]:
        s = st["steps"].get(sd["id"])
        if not s:
            continue
        mark = {"done": "✔", "blocked": "✖"}.get(s["status"], "…" if s["status"] != "pending" else "・")
        line = f" {mark} {sd['id']}（{sd.get('title', sd['id'])}）: {LABEL[s['status']]}"
        if s.get("rework"):
            line += f"  差し戻し{s['rework']}回"
        if s.get("shards"):
            line += "  分担: " + ", ".join(f"{k}={'提出済' if v == 'submitted' else '作業中'}" for k, v in s["shards"].items())
        if s["status"] == "blocked":
            line += f"  理由: {s.get('blocker')}"
        elif s["status"] == "pending":
            b = waiting_on_blocked(st, p, sd["id"])
            if b:
                line += f"  前提の{b}が止まっているため待ち"
        lines.append(line)
    return "\n".join(lines)


# ---------- 遷移 ----------

def head_commit() -> str | None:
    """実行を始めた時点のコミット。実装のゲートが「何を変えたか」をここからの差分で見る。"""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LOOP_DIR.parent.parent, capture_output=True, text=True)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except OSError:
        return None


def preexisting_changes() -> list[str]:
    """実行を始めた時点で既にあった未コミットの変更と追跡外のファイル。範囲の検査はこれを数えない。"""
    out = []
    for args in (["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        try:
            r = subprocess.run(["git", *args], cwd=LOOP_DIR.parent.parent, capture_output=True, text=True)
        except OSError:
            return []
        if r.returncode == 0:
            out += [x for x in r.stdout.splitlines() if x]
    return sorted(set(out))


def cmd_begin(a):
    p = pipeline()
    with locked():
        old = load_json(STATE)
        if old and old.get("active") and not a.force:
            raise LoopError("進行中の実行があります。続けるなら `resume`、捨てて始め直すなら `begin --force`")
        st = {
            "run_id": time.strftime("%Y%m%d-%H%M%S", time.localtime(now())),
            "active": True,
            "finished": False,
            "started_at": now(),
            "base_commit": head_commit(),
            "base_preexisting": preexisting_changes(),
            "goal": a.goal or "",
            "steps": {s["id"]: {"status": "pending", "shards": {}, "rework": 0, "notes": [], "blocker": None}
                      for s in p["steps"] if not a.only or s["id"] in a.only},
            "stop_guard": {"count": 0, "fingerprint": ""},
        }
        save_json(STATE, st)
    print(render(st, p))


def cmd_status(a):
    st, p = state(), pipeline()
    if a.json:
        print(json.dumps({"state": st, "open": open_items(st, p), "blocked": blocked_items(st)}, ensure_ascii=False, indent=2))
    else:
        print(render(st, p))


def cmd_next(a):
    """いま着手できる工程（前提が済み・未着手か作業中）を出す。統括役はこれで次の一手を決める。"""
    st, p = state(), pipeline()
    ready = []
    for sd in p["steps"]:
        s = st["steps"].get(sd["id"])
        if not s or s["status"] in ("done", "blocked"):
            continue
        if all(st["steps"].get(d, {"status": "done"})["status"] == "done" for d in after_of(p, sd["id"])):
            ready.append({"id": sd["id"], "status": s["status"], "worker": sd.get("worker"),
                          "reviewer": sd.get("reviewer"), "parallel": sd.get("parallel", 1)})
    print(json.dumps(ready, ensure_ascii=False, indent=2))


def cmd_start(a):
    p = pipeline()
    with locked():
        st = state()
        s = st_step(st, a.step)
        for d in after_of(p, a.step):
            if d in st["steps"] and st["steps"][d]["status"] != "done":
                raise LoopError(f"{a.step} はまだ始められません。先に {d} が完了している必要があります（いま {LABEL[st['steps'][d]['status']]}）")
        if s["status"] == "done":
            raise LoopError(f"{a.step} は完了済みです。やり直すなら `reopen {a.step}`")
        if s["status"] == "blocked":
            raise LoopError(f"{a.step} は止まっています（{s.get('blocker')}）。解けたら `unblock {a.step}`")
        if s["status"] in ("review", "gate", "judge"):
            raise LoopError(f"{a.step} は提出済みです（いま {LABEL[s['status']]}）。やり直すなら `reopen {a.step}`")
        s["status"] = "in_progress"
        s["shards"][a.shard] = "working"
        note(s, f"着手 shard={a.shard}")
        save_json(STATE, st)
    print(f"{a.step} を作業中にしました（shard={a.shard}）")


def cmd_submit(a):
    p = pipeline()
    with locked():
        st = state()
        s = st_step(st, a.step)
        if s["status"] != "in_progress":
            raise LoopError(f"{a.step} は作業中ではありません（いま {LABEL[s['status']]}）")
        s["shards"][a.shard] = "submitted"
        note(s, f"提出 shard={a.shard}" + (f": {a.summary}" if a.summary else ""))
        waiting = [k for k, v in s["shards"].items() if v != "submitted"]
        if not waiting:
            s["status"] = "review" if step_def(p, a.step).get("reviewer") else "gate"
        save_json(STATE, st)
    print(f"{a.step}: {LABEL[s['status']]}" + (f"（残りの分担: {', '.join(waiting)}）" if waiting else ""))


def back_to_work(s: dict, p: dict, why: str) -> None:
    s["rework"] = s.get("rework", 0) + 1
    s["shards"] = {}
    if s["rework"] > p.get("max_rework", 3):
        s["status"] = "blocked"
        s["blocker"] = f"差し戻しが上限（{p.get('max_rework', 3)}回）を超えました。直近の理由: {why}"
    else:
        s["status"] = "in_progress"
    note(s, f"差し戻し: {why}")


def cmd_review(a):
    p = pipeline()
    with locked():
        st = state()
        s = st_step(st, a.step)
        if s["status"] != "review":
            raise LoopError(f"{a.step} はレビュー待ちではありません（いま {LABEL[s['status']]}）")
        if a.verdict == "pass":
            s["status"] = "gate"
            note(s, "レビュー通過" + (f": {a.note}" if a.note else ""))
        else:
            back_to_work(s, p, f"レビュー: {a.note or '指摘あり'}")
        save_json(STATE, st)
    print(f"{a.step}: {LABEL[s['status']]}")


def run_gate(p: dict, sid: str) -> tuple[bool, str]:
    sd = step_def(p, sid)
    gate = sd.get("gate")
    if not gate:
        return True, "（この工程に決定論ゲートはありません）"
    path = (LOOP_DIR / gate).resolve()
    if not path.exists():
        return False, f"ゲート {gate} がありません"
    st = load_json(STATE, {}) or {}
    env = dict(os.environ, LOOP_STEP=sid, LOOP_DIR=str(LOOP_DIR), REPO_ROOT=str(LOOP_DIR.parent.parent),
               LOOP_BASE_COMMIT=st.get("base_commit") or "")
    try:
        r = subprocess.run(["bash", str(path)], cwd=LOOP_DIR.parent.parent, env=env,
                           capture_output=True, text=True, timeout=sd.get("gate_timeout", 1800))
    except subprocess.TimeoutExpired:
        return False, "ゲートが時間切れになりました"
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, out[-4000:]


def gate_reason(out: str) -> str:
    """差し戻しの理由。✖の付いた行（何が足りないか）を集める。無ければ最後の行。"""
    ng = [l.strip() for l in out.splitlines() if l.strip().startswith("✖")]
    if ng:
        return " / ".join(ng)[:1500]
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else "（出力なし）"


def cmd_gate(a):
    p = pipeline()
    st = state()
    if st_step(st, a.step)["status"] != "gate":
        raise LoopError(f"{a.step} はゲート待ちではありません（いま {LABEL[st['steps'][a.step]['status']]}）")
    ok, out = run_gate(p, a.step)  # ゲートは長く走りうるのでロックの外で実行する
    promoted = [r for r in load_rules() if r["status"] == "promoted" and r["step"] == a.step]
    if promoted:
        lines = ["判断役から昇格したルール:"]
        for r in promoted:
            passed, msg = rl.evaluate(r["check"], REPO)
            lines.append(f"  {'✔' if passed else '✖'} {r['id']}（問い{r['question']}）: {msg}")
            ok = ok and passed
        out = out + "\n" + "\n".join(lines)
    with locked():
        st = state()
        s = st_step(st, a.step)
        if ok:
            s["status"] = "judge" if step_def(p, a.step).get("judge_questions") else "done"
            note(s, "決定論ゲート通過")
        else:
            back_to_work(s, p, "決定論ゲート不合格: " + gate_reason(out))
        save_json(STATE, st)
    print(out)
    print(f"--- ゲート{'通過' if ok else '不合格'} → {a.step}: {LABEL[s['status']]}")
    sys.exit(0 if ok else 1)


# ---------- 判断役 ----------

def thresholds(p: dict) -> dict:
    cal = load_json(CALIBRATION, {}) or {}
    return cal.get("thresholds", {})


def audit_pick(jid: str, rate: float) -> bool:
    """自動で通した判断の一部を人の確認へ回す（学習の材料を絶やさないため）。乱数でなくidのハッシュで決める。"""
    if rate <= 0:
        return False
    h = int(hashlib.sha256(jid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < rate


def cmd_judge(a):
    p = pipeline()
    cfg = p.get("judge", {})
    default_th = cfg.get("default_threshold", 0.9)
    rate = cfg.get("audit_rate", 0.0)
    try:
        payload = json.loads(Path(a.answers[1:]).read_text() if a.answers.startswith("@") else a.answers)
    except (json.JSONDecodeError, OSError) as e:
        raise LoopError(f"--answers をJSONとして読めません: {e}")
    got = {x["id"]: x for x in payload.get("answers", [])}
    ths = thresholds(p)
    with locked():
        st = state()
        s = st_step(st, a.step)
        if s["status"] != "judge":
            raise LoopError(f"{a.step} は判断待ちではありません（いま {LABEL[s['status']]}）")
        results, rows = [], []
        all_rules = load_rules()
        new_rules = []
        for q in step_def(p, a.step)["judge_questions"]:
            ans = got.get(q["id"])
            cand = (ans or {}).get("rule_candidate")
            if cand and ans.get("answer") != q["pass"]:
                err = rl.validate(cand)
                rid = rl.rule_id(q["id"], cand) if not err else None
                if err:
                    note(s, f"判断役のルール候補を捨てた（{q['id']}）: {err}")
                elif not any(r["id"] == rid for r in all_rules + new_rules):
                    new_rules.append({"id": rid, "step": a.step, "question": q["id"], "check": cand,
                                      "status": "shadow", "created": now(), "origin": st["run_id"]})
            jid = f"{st['run_id']}-{a.step}-{q['id']}-r{s.get('rework', 0)}"
            if ans is None or ans.get("answer") not in q["answers"]:
                decision = "escalate"
                reason = "回答が無いか、選択肢の外"
                conf = 0.0
                answer = ans.get("answer") if ans else None
            else:
                answer, conf = ans["answer"], float(ans.get("confidence", 0))
                th = ths.get(q["id"], default_th)
                if conf < th:
                    decision, reason = "escalate", f"確信度{conf:.2f}が閾値{th:.2f}未満"
                elif answer == q["pass"]:
                    decision, reason = "auto_pass", f"確信度{conf:.2f}≧{th:.2f}"
                    if audit_pick(jid, rate):
                        decision, reason = "escalate", "抜き取り確認（学習用）"
                else:
                    decision, reason = "auto_fail", f"確信度{conf:.2f}≧{th:.2f}"
            shadow = {r["id"]: not rl.evaluate(r["check"], REPO)[0]
                      for r in all_rules + new_rules if r["status"] == "shadow" and r["question"] == q["id"]}
            rows.append({"id": jid, "t": now(), "run": st["run_id"], "step": a.step, "question": q["id"], "shadow": shadow,
                         "rework": s.get("rework", 0), "answer": answer, "pass_answer": q["pass"], "confidence": conf, "decision": decision,
                         "judge_reason": (ans or {}).get("reason", ""), "human_answer": None, "note": ""})
            results.append((q, answer, decision, reason, (ans or {}).get("reason", "")))
        if any(r[2] == "auto_fail" for r in results):
            why = "; ".join(f"{q['id']}={ans}（{jr}）" for q, ans, d, _, jr in results if d == "auto_fail")
            back_to_work(s, p, f"判断役: {why}")
        elif any(r[2] == "escalate" for r in results):
            s["status"] = "blocked"
            s["needs_human"] = True
            s["blocker"] = "判断役が自信を持てない項目があり、人の判断待ち: " + ", ".join(
                f"{q['id']}（{rs}）" for q, _, d, rs, _ in results if d == "escalate")
        else:
            s["status"] = "done"
        note(s, "判断役: " + ", ".join(f"{q['id']}={d}" for q, _, d, _, _ in results))
        JUDGE_DIR.mkdir(parents=True, exist_ok=True)
        if new_rules:
            save_rules(all_rules + new_rules)
            note(s, "判断役のルール候補を影で走らせ始めた: " + ", ".join(r["id"] for r in new_rules))
        with open(JUDGMENTS, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        save_json(STATE, st)
    for q, ans, d, rs, jr in results:
        print(f"{q['id']}: {ans} → {d}（{rs}）")
    print(f"--- {a.step}: {LABEL[s['status']]}")


def rewrite_judgments(fn) -> int:
    if not JUDGMENTS.exists():
        return 0
    rows = [json.loads(l) for l in JUDGMENTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = 0
    for r in rows:
        if fn(r):
            n += 1
    JUDGMENTS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return n


def cmd_decide(a):
    """人が止まっている判断を裁く。判断役の回答に正解ラベルが付き、較正の材料になる。"""
    p = pipeline()
    with locked():
        st = state()
        s = st_step(st, a.step)
        if not s.get("needs_human"):
            raise LoopError(f"{a.step} は人の判断待ちではありません")
        q_pass = {q["id"]: q["pass"] for q in step_def(p, a.step)["judge_questions"]}
        rw = s.get("rework", 0)

        def label(r):
            if (r.get("run") == st["run_id"] and r.get("step") == a.step and r.get("human_answer") is None
                    and r.get("rework", rw) == rw):
                if a.verdict == "pass":
                    r["human_answer"] = q_pass[r["question"]]
                elif a.fail_questions and r["question"] not in a.fail_questions:
                    r["human_answer"] = q_pass[r["question"]]
                else:
                    r["human_answer"] = f"not:{q_pass[r['question']]}"
                r["note"] = a.note or ""
                return True
            return False

        n = rewrite_judgments(label)
        s["needs_human"] = False
        s["blocker"] = None
        if a.verdict == "pass":
            s["status"] = "done"
            note(s, f"人が通過と判断: {a.note or ''}")
        else:
            back_to_work(s, p, f"人の判断で差し戻し: {a.note or ''}")
        save_json(STATE, st)
    print(f"{a.step}: {LABEL[s['status']]}（{n}件の判断に正解を付けました）")


def cmd_override(a):
    """自動で決まった判断を、後から人が訂正する（誤りの例として学習に使う）。"""
    def fix(r):
        if r["id"] == a.judgment_id:
            r["human_answer"] = a.answer
            r["note"] = a.note or ""
            return True
        return False
    n = rewrite_judgments(fix)
    if not n:
        raise LoopError(f"判断 {a.judgment_id} は judgments.jsonl にありません")
    print(f"{a.judgment_id} に正解 {a.answer} を記録しました。`calibrate` で閾値と誤り例へ反映されます")


def correct(r) -> bool:
    h = r["human_answer"]
    if h.startswith("not:"):
        return r["answer"] != h[4:]
    return r["answer"] == h


def cmd_calibrate(a):
    """人が正解を付けた判断から、問いごとに「自動で任せてよい確信度」を求める。

    閾値t = 確信度t以上の標本の正答率が目標以上で、かつ標本数が下限以上になる最小のt。
    満たすtが無い問いは自動にしない（閾値1.01＝常に人へ回す）。
    """
    p = pipeline()
    cfg = p.get("judge", {})
    target = a.target or cfg.get("target_accuracy", 0.95)
    min_n = a.min_samples or cfg.get("min_samples", 20)
    rows = [json.loads(l) for l in JUDGMENTS.read_text(encoding="utf-8").splitlines() if l.strip()] if JUDGMENTS.exists() else []
    labeled = [r for r in rows if r.get("human_answer") and r.get("answer") is not None]
    by_q: dict[str, list] = {}
    for r in labeled:
        by_q.setdefault(r["question"], []).append(r)
    out, report = {}, []
    for qid, rs in sorted(by_q.items()):
        rs.sort(key=lambda r: -r["confidence"])
        best = None
        ok = 0
        for i, r in enumerate(rs, 1):
            ok += correct(r)
            # 同じ確信度が並ぶ間は判定しない（「t以上の標本すべて」で数えるため、境目でだけ見る）
            if i < len(rs) and rs[i]["confidence"] == r["confidence"]:
                continue
            if i >= min_n and ok / i >= target:
                best = r["confidence"]
        acc = sum(correct(r) for r in rs) / len(rs)
        out[qid] = best if best is not None else 1.01
        report.append(f"{qid}: 標本{len(rs)}件 正答率{acc:.0%} → 閾値 " + (f"{best:.2f}" if best is not None else "なし（人へ回す）"))
    wrong = [r for r in labeled if not correct(r)][-a.lessons:]
    print("\n".join(report) or "正解の付いた判断がまだありません（`decide` / `override` で付きます）")
    if a.apply:
        save_json(CALIBRATION, {"updated": now(), "target_accuracy": target, "min_samples": min_n, "thresholds": out})
        body = ["# 判断役が過去に誤った例（calibrateが自動で書く・手で直さない）", "",
                "同じ形の判断では、ここに挙がった誤りを繰り返さないこと。", ""]
        for r in wrong:
            body.append(f"- 問い`{r['question']}`（工程{r['step']}）: 判断役は`{r['answer']}`・確信度{r['confidence']:.2f}"
                        f" → 正しくは`{r['human_answer']}`。判断役の理由: {r.get('judge_reason', '')}。人の注記: {r.get('note', '')}")
        LESSONS.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"反映しました: {CALIBRATION.name}・{LESSONS.name}（誤りの例{len(wrong)}件）")
    else:
        print("（確認だけ。反映するなら --apply）")


# ---------- 判断役から決定論への昇格 ----------

def load_rules() -> list:
    return (load_json(RULES, {}) or {}).get("rules", [])


def save_rules(rs: list) -> None:
    save_json(RULES, {"rules": rs})


def truth_pass(r: dict):
    """その判断の「正しい答えは合格だったか」。人の正解を優先し、無ければ自動で決まった結論。分からなければNone。"""
    h = r.get("human_answer")
    if h:
        return (not h.startswith("not:")) and h == r.get("pass_answer", h)
    return {"auto_pass": True, "auto_fail": False}.get(r.get("decision"))


def rule_stats(rid: str) -> dict:
    """影で走った実績。fired=不合格を検出した回数、fp=検出したのに正しい答えは合格だった回数（誤検出）。"""
    st = {"fired": 0, "tp": 0, "fp": 0, "unknown": 0, "missed": 0, "seen": 0}
    if not JUDGMENTS.exists():
        return st
    for l in JUDGMENTS.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if rid not in r.get("shadow", {}):
            continue
        st["seen"] += 1
        t = truth_pass(r)
        if r["shadow"][rid]:
            st["fired"] += 1
            st["unknown" if t is None else "fp" if t else "tp"] += 1
        elif t is False:
            st["missed"] += 1
    return st


def cmd_rules(a):
    p = pipeline()
    need = p.get("judge", {}).get("promote_min_fires", 5)
    rs = load_rules()
    if not rs:
        print("ルールの候補はまだありません（判断役が機械的な理由で不合格を出すと、候補が添えられます）")
        return
    for r in rs:
        s = rule_stats(r["id"])
        ready = r["status"] == "shadow" and s["tp"] >= need and s["fp"] == 0
        mark = {"promoted": "採用中", "retired": "廃止", "shadow": "影で検証中"}[r["status"]]
        print(f"{r['id']} [{mark}] 工程{r['step']}・問い{r['question']}: {rl.describe(r['check'])} で不合格を検出")
        print(f"    実績: 検出{s['fired']}回（正しい{s['tp']}・誤り{s['fp']}・未確定{s['unknown']}）、見逃し{s['missed']}回")
        if ready:
            print(f"    → 昇格の条件を満たしました（正しい検出{need}回以上・誤りなし）。採用するなら `loopctl.py promote {r['id']}`")
        elif r["status"] == "shadow" and s["fp"]:
            print(f"    → 誤検出があります。廃止するなら `loopctl.py retire {r['id']}`")


def set_rule_status(rid: str, status: str, force: bool = False) -> dict:
    rs = load_rules()
    for r in rs:
        if r["id"] == rid:
            if status == "promoted" and not force:
                s = rule_stats(rid)
                need = pipeline().get("judge", {}).get("promote_min_fires", 5)
                if s["fp"] or s["tp"] < need:
                    raise LoopError(f"{rid} は昇格の条件を満たしていません（正しい検出{s['tp']}/{need}回・誤り{s['fp']}回）。承知で採るなら --force")
            r["status"] = status
            r[f"{status}_at"] = now()
            save_rules(rs)
            return r
    raise LoopError(f"ルール {rid} はありません（`loopctl.py rules`で一覧）")


def cmd_promote(a):
    r = set_rule_status(a.rule_id, "promoted", a.force)
    print(f"{r['id']} を採用しました。以後、工程{r['step']}の決定論ゲートで「{rl.describe(r['check'])}」を確かめます")


def cmd_retire(a):
    r = set_rule_status(a.rule_id, "retired")
    print(f"{r['id']} を廃止しました")


# ---------- その他の遷移 ----------

def cmd_block(a):
    with locked():
        st = state()
        s = st_step(st, a.step)
        s["status"] = "blocked"
        s["blocker"] = a.reason
        note(s, f"停止: {a.reason}")
        save_json(STATE, st)
    print(f"{a.step} を止めました: {a.reason}")


def cmd_unblock(a):
    with locked():
        st = state()
        s = st_step(st, a.step)
        if s["status"] != "blocked":
            raise LoopError(f"{a.step} は止まっていません")
        s["status"] = "in_progress"
        s["blocker"] = None
        s["needs_human"] = False
        s["shards"] = {}
        note(s, f"再開: {a.note or ''}")
        save_json(STATE, st)
    print(f"{a.step} を作業中へ戻しました")


def cmd_reopen(a):
    with locked():
        st = state()
        s = st_step(st, a.step)
        s["status"] = "in_progress"
        s["shards"] = {}
        note(s, f"やり直し: {a.note or ''}")
        save_json(STATE, st)
    print(f"{a.step} をやり直しにしました")


def set_active(flag: bool, msg: str, finished: bool = False):
    with locked():
        st = state()
        st["active"] = flag
        st["finished"] = finished
        st.pop("halted", None)
        st["stop_guard"] = {"count": 0, "fingerprint": ""}
        save_json(STATE, st)
    print(msg)


def main(argv=None):
    ap = argparse.ArgumentParser(description="ループの状態を機械で動かす")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin", help="実行を始める")
    b.add_argument("--goal", help="今回の完了条件（GOAL.mdの要約）")
    b.add_argument("--only", nargs="*", help="この工程だけで実行する")
    b.add_argument("--force", action="store_true")
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    sub.add_parser("next", help="いま着手できる工程")
    for name in ("start", "submit"):
        x = sub.add_parser(name); x.add_argument("step"); x.add_argument("--shard", default="main")
        if name == "submit":
            x.add_argument("--summary", default="")
    r = sub.add_parser("review"); r.add_argument("step"); r.add_argument("verdict", choices=["pass", "fail"]); r.add_argument("--note", default="")
    g = sub.add_parser("gate"); g.add_argument("step")
    j = sub.add_parser("judge"); j.add_argument("step"); j.add_argument("--answers", required=True, help="JSON文字列、または@ファイル")
    d = sub.add_parser("decide", help="人の判断待ちを裁く"); d.add_argument("step"); d.add_argument("verdict", choices=["pass", "fail"])
    d.add_argument("--note", default=""); d.add_argument("--fail-questions", nargs="*", help="failの時、誤っていた問いのid（省略時は全部）")
    o = sub.add_parser("override", help="自動判断を後から訂正"); o.add_argument("judgment_id"); o.add_argument("answer"); o.add_argument("--note", default="")
    c = sub.add_parser("calibrate"); c.add_argument("--apply", action="store_true"); c.add_argument("--target", type=float)
    c.add_argument("--min-samples", type=int); c.add_argument("--lessons", type=int, default=20)
    sub.add_parser("rules", help="判断役から出たルールの候補と実績")
    pr = sub.add_parser("promote", help="ルールを決定論ゲートへ採用する（人が承認）"); pr.add_argument("rule_id"); pr.add_argument("--force", action="store_true")
    rt = sub.add_parser("retire", help="ルールを廃止する"); rt.add_argument("rule_id")
    bl = sub.add_parser("block"); bl.add_argument("step"); bl.add_argument("reason")
    ub = sub.add_parser("unblock"); ub.add_argument("step"); ub.add_argument("--note", default="")
    ro = sub.add_parser("reopen"); ro.add_argument("step"); ro.add_argument("--note", default="")
    sub.add_parser("pause", help="Stopフックの催促を止める（人が付き添う時）")
    sub.add_parser("resume", help="催促を再開する")
    sub.add_parser("finish", help="実行を閉じる")
    a = ap.parse_args(argv)
    try:
        {
            "begin": cmd_begin, "status": cmd_status, "next": cmd_next, "start": cmd_start, "submit": cmd_submit,
            "review": cmd_review, "gate": cmd_gate, "judge": cmd_judge, "decide": cmd_decide, "override": cmd_override,
            "calibrate": cmd_calibrate, "rules": cmd_rules, "promote": cmd_promote, "retire": cmd_retire, "block": cmd_block, "unblock": cmd_unblock, "reopen": cmd_reopen,
            "pause": lambda a: set_active(False, "一時停止しました（Stopフックは催促しません）"),
            "resume": lambda a: set_active(True, "再開しました"),
            "finish": lambda a: set_active(False, "実行を閉じました", finished=True),
        }[a.cmd](a)
    except LoopError as e:
        print(f"loopctl: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
