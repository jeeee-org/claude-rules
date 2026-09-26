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
import re
import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from fnmatch import fnmatch
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
GATE_STATS = LOOP_DIR / "stats" / "gates.jsonl"
# 実行中に工程役が書き換えてはいけない、ループ自身のファイル（改善案6: ループの中でループを改修しない）
SELF_FILES = ("bin/*.py", "gates/*", "pipeline.json", "../agents/*.md", "../settings.json")
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


ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def subst(x, item: str):
    """工程の型の中の {item} を項目idに置き換える（文字列・配列・辞書を辿る）。"""
    if isinstance(x, str):
        return x.replace("{item}", item)
    if isinstance(x, list):
        return [subst(v, item) for v in x]
    if isinstance(x, dict):
        return {k: subst(v, item) for k, v in x.items()}
    return x


def expand(raw: dict, items: list[str]) -> dict:
    """per_item（工程の型）を項目ごとに展開し、`<項目>/<工程>`の工程として steps の後ろへ並べる。

    項目の中では、型の工程は既定で直前の型の工程を前提にする。最初の工程の前提は per_item.after。
    per_item.serial が真なら、各項目の最初の工程は前の項目の最後の工程も前提にする（一覧の順に1件ずつ。
    同じ場所を触る項目を並列にしない。前の項目が止まれば後ろは待つ）。
    判断役の問いのidは項目をまたいで同じままにする（較正と誤りの例を項目の間で共有するため）。
    """
    pi = raw.get("per_item")
    if not pi:
        return raw
    p = dict(raw)
    steps = list(raw.get("steps", []))
    tmpl = pi.get("steps", [])
    tids = [t["id"] for t in tmpl]
    prev_last = None
    for it in items:
        for i, t in enumerate(tmpl):
            sd = subst(t, it)
            sd["id"] = f"{it}/{t['id']}"
            sd["template"], sd["item"] = t["id"], it
            if "after" in t:
                sd["after"] = [f"{it}/{d}" if d in tids else d for d in t["after"]]
            else:
                sd["after"] = [f"{it}/{tids[i - 1]}"] if i else list(pi.get("after", []))
            if i == 0 and pi.get("serial") and prev_last:
                sd["after"].append(prev_last)
            steps.append(sd)
        prev_last = f"{it}/{tids[-1]}" if tids else prev_last
    p["steps"] = steps
    return p


def pipeline(items: list[str] | None = None) -> dict:
    raw = load_json(PIPELINE)
    if raw is None:
        raise LoopError(f"{PIPELINE} がありません")
    if raw.get("per_item") and items is None:
        # 項目の一覧は実行の状態に持つ（実行中に足しても pipeline.json＝ループ自身を書き換えずに済む）
        st = load_json(STATE)
        items = st["items"] if st and "items" in st else raw["per_item"].get("items", [])
    p = expand(raw, items or [])
    st = load_json(STATE)
    if st and st.get("limit_override"):
        p = with_overrides(p, st["limit_override"])
    ids = [s["id"] for s in p.get("steps", [])]
    if len(ids) != len(set(ids)):
        raise LoopError("pipeline.json の工程idが重複しています")
    return p


TOP_LIMITS = ("time_budget_sec", "max_rework", "max_auto_continues")


def with_overrides(p: dict, ov: dict) -> dict:
    """`begin --limit` で、この実行の間だけ差し替えた上限を当てる（pipeline.json＝ループ自身は書き換えない）。"""
    p = dict(p)
    p["limits"] = dict(p.get("limits", {}))
    for k, v in ov.items():
        if k in TOP_LIMITS:
            p[k] = v
        else:
            p["limits"][k] = v
    return p


def parse_limits(pairs: list[str] | None, raw: dict) -> dict:
    out = {}
    known = set(raw.get("limits", {})) | set(TOP_LIMITS) | {"time_budget_hard", "max_total_rework", "max_shards", "max_items"}
    for x in pairs or []:
        if "=" not in x:
            raise LoopError(f"--limit は <名前>=<値> の形で渡す（{x}）")
        k, v = x.split("=", 1)
        if k not in known:
            raise LoopError(f"--limit の {k} は上限の名前ではありません（使えるのは {', '.join(sorted(known))}）")
        try:
            out[k] = json.loads(v)
        except ValueError:
            raise LoopError(f"--limit の値 {v} を読めません（数・true/false・null）")
    return out


def step_def(p: dict, sid: str) -> dict:
    for s in p["steps"]:
        if s["id"] == sid:
            return s
    raise LoopError(f"工程 {sid} は pipeline.json にありません（あるのは {', '.join(x['id'] for x in p['steps'])}）")


def after_of(p: dict, sid: str) -> list[str]:
    """先に終わっているべき工程。書かなければ直前の工程1つ。"""
    s = step_def(p, sid)
    if "after" in s:
        out = []
        for d in s["after"]:
            if any(c in d for c in "*?["):  # 例: "*/record" = 全項目の record を待つ
                out += [x["id"] for x in p["steps"] if x["id"] != sid and fnmatch(x["id"], d)]
            else:
                out.append(d)
        return out
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
    if st.get("limit_override"):
        lines.append("※ この実行だけ上限を差し替え: " + ", ".join(f"{k}={json.dumps(v)}" for k, v in st["limit_override"].items()))
    why = limit_reason(st, p) if st.get("active") else None
    if why:
        lines.append(f"※ {why}（次の着手で止まります）")
    if st.get("halted"):
        lines.append(f"※ {st['halted']}（`resume`で再開）")
    el = int(now() - st["started_at"])
    budget = effective_budget(st, p)
    lines.append(f"経過 {el}s" + (f" / 予算 {budget}s" if budget else "")
                 + (f"（延長{st['budget_extra']}sを含む）" if st.get("budget_extra") else ""))
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
            if s.get("ask"):
                line += f"（選択肢: {' / '.join(s['ask']['options'])}・推奨: {s['ask'].get('recommend') or 'なし'}）"
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


def self_snapshot() -> dict:
    """ループ自身のファイルのハッシュ。実行開始時に控え、ゲートのたびに突き合わせる。"""
    snap = {}
    for pat in SELF_FILES:
        for f in sorted(LOOP_DIR.glob(pat)):
            if f.is_file() and "__pycache__" not in f.parts:
                snap[str(f.resolve().relative_to(REPO))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return snap


def self_changes(st: dict) -> list[str]:
    base = st.get("self_snapshot")
    if base is None:
        return []
    now_ = self_snapshot()
    return sorted(k for k in set(base) | set(now_) if base.get(k) != now_.get(k))


def effective_budget(st: dict, p: dict):
    """時間の予算。`resume --extend` で延ばした分を足す。"""
    b = p.get("time_budget_sec")
    return b + st.get("budget_extra", 0) if b else b


def limit_reason(st: dict, p: dict, adding_shard: int = 0) -> str | None:
    """実行全体の上限（改善案2）。1工程・1停止の単位でなく、実行全体で数える。"""
    lim = p.get("limits", {})
    budget = effective_budget(st, p)
    if budget and lim.get("time_budget_hard") and now() - st["started_at"] > budget:
        return f"時間の上限（{budget}s）を超えました"
    total = sum(x.get("rework", 0) for x in st["steps"].values())
    if lim.get("max_total_rework") is not None and total > lim["max_total_rework"]:
        return f"実行全体の差し戻しが上限（{lim['max_total_rework']}回）を超えました"
    if lim.get("max_shards") is not None and st.get("shards_started", 0) + adding_shard > lim["max_shards"]:
        return f"着手した分担の数が上限（{lim['max_shards']}）を超えました"
    return None


def halt(st: dict, reason: str) -> None:
    st["active"] = False
    st["halted"] = reason


def cmd_begin(a):
    raw = load_json(PIPELINE)
    if raw is None:
        raise LoopError(f"{PIPELINE} がありません")
    items = None
    override = parse_limits(a.limit, raw)
    if raw.get("per_item"):
        pi = raw["per_item"]
        if a.items or a.items_file:
            items = read_items(a)
        elif pi.get("items_file"):
            # 一覧のファイルは pipeline.json に置き場だけを書く（中身は実行の状態に写す。実行中の add-item は状態へ）
            f = REPO / pi["items_file"]
            if not f.exists():
                raise LoopError(f"per_item.items_file の {pi['items_file']} がありません（リポのルートからのパス）")
            items = parse_items_text(f.read_text(encoding="utf-8"))
        else:
            items = list(pi.get("items", []))
        check_items(items, raw)
        if not items and not a.allow_empty:
            raise LoopError("項目が0件です。一覧を渡すか（`--items-file <一覧>`、または pipeline.json の per_item.items_file）、"
                            "0件で始めて後から `add-item` するなら --allow-empty")
    with locked():
        old = load_json(STATE)
        if old and old.get("active") and not a.force:
            raise LoopError("進行中の実行があります。続けるなら `resume`、捨てて始め直すなら `begin --force`")
    p = expand(raw, items or [])
    if override:
        p = with_overrides(p, override)
    ids = [x["id"] for x in p.get("steps", [])]
    if len(ids) != len(set(ids)):
        raise LoopError("pipeline.json の工程idが重複しています")
    with locked():
        st = {
            "run_id": time.strftime("%Y%m%d-%H%M%S", time.localtime(now())),
            "active": True,
            "finished": False,
            "started_at": now(),
            "base_commit": head_commit(),
            "base_preexisting": preexisting_changes(),
            "self_snapshot": self_snapshot(),
            "shards_started": 0,
            "goal": a.goal or "",
            "steps": {s["id"]: {"status": "pending", "shards": {}, "rework": 0, "notes": [], "blocker": None}
                      for s in p["steps"] if not a.only or s["id"] in a.only},
            "stop_guard": {"count": 0, "fingerprint": ""},
            "nudges_total": 0,
        }
        if override:
            st["limit_override"] = override
        if items is not None:
            st["items"] = items
        save_json(STATE, st)
    print(render(st, p))


def parse_items_text(text: str) -> list[str]:
    """項目の一覧（JSONの配列、または1行1件。#で始まる行と空行は読まない）。"""
    try:
        return [str(x) for x in json.loads(text)]
    except ValueError:
        return [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def read_items(a) -> list[str]:
    items = list(a.items or [])
    if a.items_file:
        items += parse_items_text(Path(a.items_file).read_text(encoding="utf-8"))
    return items


def check_items(items: list[str], raw: dict) -> None:
    bad = [x for x in items if not ITEM_RE.match(x)]
    if bad:
        raise LoopError(f"項目idに使えない文字があります: {', '.join(bad)}（英数字と . _ - だけ）")
    if len(items) != len(set(items)):
        raise LoopError("項目idが重複しています")
    cap = raw.get("limits", {}).get("max_items")
    if cap is not None and len(items) > cap:
        raise LoopError(f"項目の数が上限（limits.max_items={cap}）を超えます（{len(items)}件）")


def cmd_add_item(a):
    """実行中に項目を足す。pipeline.json（ループ自身）は書き換えず、状態の項目一覧へ足して工程を展開する。"""
    raw = load_json(PIPELINE) or {}
    if not raw.get("per_item"):
        raise LoopError("pipeline.json に per_item（工程の型）がありません")
    with locked():
        st = state()
        cur = list(st.get("items", []))
        new = [x for x in read_items(a) if x not in cur]
        check_items(cur + new, raw)
        st["items"] = cur + new
        p = pipeline(items=st["items"])
        for sd in p["steps"]:
            if sd["id"] not in st["steps"]:
                st["steps"][sd["id"]] = {"status": "pending", "shards": {}, "rework": 0, "notes": [], "blocker": None}
        save_json(STATE, st)
    print(f"項目を{len(new)}件足しました: {', '.join(new) or '（なし。既にある）'}（全{len(st['items'])}件）")


def cmd_show(a):
    """工程の定義（項目ごとの工程は {item} を置き換えた後）を出す。工程役・レビュー役が読むためのもの。"""
    print(json.dumps(step_def(pipeline(), a.step), ensure_ascii=False, indent=2))


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
        why = limit_reason(st, p, adding_shard=1)
        if why:
            halt(st, why)
            save_json(STATE, st)
            raise LoopError(f"{why}。実行を止めました（`status`で確かめ、続けるなら上限を見直して `resume`）")
        s["status"] = "in_progress"
        s["shards"][a.shard] = "working"
        st["shards_started"] = st.get("shards_started", 0) + 1
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
               LOOP_BASE_COMMIT=st.get("base_commit") or "", LOOP_ITEM=sd.get("item", ""),
               LOOP_TEMPLATE=sd.get("template", sid), LOOP_OUTPUTS="\n".join(sd.get("outputs", [])))
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
    sd = step_def(p, a.step)
    tkey = sd.get("template", a.step)
    promoted = [r for r in load_rules() if r["status"] == "promoted" and r["step"] == tkey]
    if promoted:
        lines = ["判断役から昇格したルール:"]
        for r in promoted:
            passed, msg = rl.evaluate(for_item(r["check"], sd.get("item")), REPO)
            lines.append(f"  {'✔' if passed else '✖'} {r['id']}（問い{r['question']}）: {msg}  〔{r['id']}〕")
            ok = ok and passed
        out = out + "\n" + "\n".join(lines)
    changed_self = self_changes(state())
    if changed_self:
        out += "\nループ自身の改修（実行中は禁止。人が直したなら `loopctl.py accept-self`）:\n" + "\n".join(
            f"  ✖ {f} が実行開始後に変わった  〔loop-self〕" for f in changed_self)
        ok = False
    record_gate_stats(state()["run_id"], tkey, out)
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


def for_item(check: dict, item: str | None) -> dict:
    """ルールの検査のパスの {item} を、いま見ている項目に置き換える。"""
    if not item:
        return check
    return {**check, "args": [x.replace("{item}", item) if isinstance(x, str) else x for x in check.get("args", [])]}


def to_template(check: dict, item: str | None) -> dict:
    """判断役が書いた具体的な項目idを {item} に戻す（ルールを項目をまたいで育てるため）。"""
    if not item:
        return check
    pat = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(item) + r"(?![A-Za-z0-9_-])")
    return {**check, "args": [pat.sub("{item}", x) if isinstance(x, str) else x for x in check.get("args", [])]}


def audit_pick(jid: str, rate: float) -> bool:
    """自動で通した判断の一部を人の確認へ回す（学習の材料を絶やさないため）。乱数でなくidのハッシュで決める。"""
    if rate <= 0:
        return False
    h = int(hashlib.sha256(jid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return h < rate


def cmd_judge(a):
    p = pipeline()
    cfg = p.get("judge", {})
    # 較正前の既定。null（既定）＝較正で閾値が出た問いだけ任せ、それまでは全部人へ回す（人の答えを溜めて育てる）
    default_th = cfg.get("default_threshold")
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
        sd = step_def(p, a.step)
        item, tkey = sd.get("item"), sd.get("template", a.step)
        for q in sd["judge_questions"]:
            ans = got.get(q["id"])
            cand = (ans or {}).get("rule_candidate")
            if cand and ans.get("answer") != q["pass"]:
                err = rl.validate(cand)
                cand = to_template(cand, item) if not err else cand
                rid = rl.rule_id(q["id"], cand) if not err else None
                if err:
                    note(s, f"判断役のルール候補を捨てた（{q['id']}）: {err}")
                elif not any(r["id"] == rid for r in all_rules + new_rules):
                    new_rules.append({"id": rid, "step": tkey, "question": q["id"], "check": cand,
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
                if th is None:
                    decision, reason = "escalate", "較正前（この問いの閾値がまだ無い）なので人へ回す"
                elif conf < th:
                    decision, reason = "escalate", f"確信度{conf:.2f}が閾値{th:.2f}未満"
                elif answer == q["pass"]:
                    decision, reason = "auto_pass", f"確信度{conf:.2f}≧{th:.2f}"
                    if audit_pick(jid, rate):
                        decision, reason = "escalate", "抜き取り確認（学習用）"
                else:
                    decision, reason = "auto_fail", f"確信度{conf:.2f}≧{th:.2f}"
            shadow = {r["id"]: not rl.evaluate(for_item(r["check"], item), REPO)[0]
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


def decide_core(st: dict, p: dict, step: str, verdict: str, note_: str, fail_questions=None) -> int:
    """判断役が人へ回した工程を裁く（ロックの内側で呼ぶ）。付けた正解の件数を返す。"""
    s = st_step(st, step)
    if not s.get("needs_human") or s.get("ask"):
        raise LoopError(f"{step} は判断役からの人の判断待ちではありません" + ("（工程役の問いは `answer`）" if s.get("ask") else ""))
    q_pass = {q["id"]: q["pass"] for q in step_def(p, step)["judge_questions"]}
    rw = s.get("rework", 0)

    def label(r):
        if (r.get("run") == st["run_id"] and r.get("step") == step and r.get("human_answer") is None
                and r.get("kind") != "ask" and r.get("rework", rw) == rw):
            if verdict == "pass":
                r["human_answer"] = q_pass[r["question"]]
            elif fail_questions and r["question"] not in fail_questions:
                r["human_answer"] = q_pass[r["question"]]
            else:
                r["human_answer"] = f"not:{q_pass[r['question']]}"
            r["note"] = note_ or ""
            return True
        return False

    n = rewrite_judgments(label)
    s["needs_human"] = False
    s["blocker"] = None
    if verdict == "pass":
        s["status"] = "done"
        note(s, f"人が通過と判断: {note_ or ''}")
    else:
        back_to_work(s, p, f"人の判断で差し戻し: {note_ or ''}")
    return n


def cmd_decide(a):
    """人が止まっている判断を裁く。判断役の回答に正解ラベルが付き、較正の材料になる。"""
    p = pipeline()
    with locked():
        st = state()
        n = decide_core(st, p, a.step, a.verdict, a.note, a.fail_questions)
        s = st["steps"][a.step]
        save_json(STATE, st)
    print(f"{a.step}: {LABEL[s['status']]}（{n}件の判断に正解を付けました）")


# ---------- 人待ちの一覧と、まとめての答え ----------

def load_judgments() -> list:
    if not JUDGMENTS.exists():
        return []
    return [json.loads(l) for l in JUDGMENTS.read_text(encoding="utf-8").splitlines() if l.strip()]


def pending_list(st: dict, p: dict) -> list[dict]:
    """人が答えれば動く工程の一覧。工程役の問い・判断役が人へ回した判断・理由だけの停止の3種。"""
    rows = load_judgments()
    out = []
    for sd in p["steps"]:
        sid = sd["id"]
        s = st["steps"].get(sid)
        if not s or s["status"] != "blocked":
            continue
        if s.get("ask"):
            k = dict(s["ask"])
            out.append({"step": sid, "kind": "ask", "question": k["question"], "options": k["options"],
                        "recommend": k.get("recommend"), "judge": k.get("judge")})
        elif s.get("needs_human"):
            rw = s.get("rework", 0)
            qtext = {q["id"]: q.get("question", q["id"]) for q in sd.get("judge_questions", [])}
            qs = [r for r in rows if r.get("run") == st["run_id"] and r.get("step") == sid and r.get("kind") != "ask"
                  and r.get("human_answer") is None and r.get("rework", rw) == rw]
            rec = "pass" if qs and all(r.get("answer") == r.get("pass_answer") for r in qs) else "fail"
            out.append({"step": sid, "kind": "judge", "options": ["pass", "fail"], "recommend": rec,
                        "questions": [{"id": r["question"], "question": qtext.get(r["question"], r["question"]),
                                       "judge_answer": r.get("answer"), "confidence": r.get("confidence"),
                                       "judge_reason": r.get("judge_reason", ""), "why_human": r.get("decision")}
                                      for r in qs]})
        else:
            out.append({"step": sid, "kind": "blocked", "reason": s.get("blocker") or "理由未記入"})
    return out


def cmd_pending(a):
    st, p = state(), pipeline()
    items = pending_list(st, p)
    if a.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if not items:
        print("人待ちはありません")
        return
    for i, x in enumerate(items, 1):
        if x["kind"] == "ask":
            j = x.get("judge") or {}
            print(f"[{i}] {x['step']}（工程役の問い）{x['question']}")
            print(f"    選択肢: {' / '.join(x['options'])}  推奨: {x.get('recommend') or '（なし）'}"
                  + (f"  判断役: {j.get('answer')}（確信度{j.get('confidence', 0):.2f}）{j.get('reason', '')}" if j.get("answer") else ""))
        elif x["kind"] == "judge":
            print(f"[{i}] {x['step']}（判断役が人へ回した）推奨: {x['recommend']}")
            for q in x["questions"]:
                print(f"    問い{q['id']}: {q['question']}  判断役: {q['judge_answer']}（確信度{q['confidence'] or 0:.2f}）{q['judge_reason']}")
        else:
            print(f"[{i}] {x['step']}（止まっている）理由: {x['reason']}  → 解けたら `unblock {x['step']}`")
    print("\n答え方: `loopctl.py answer <工程>=<選択肢> ...`（判断役の分は pass|fail）。推奨どおりなら `<工程>=推奨`、"
          "全部推奨どおりなら `answer --recommended`。どれを選んだかは judge/judgments.jsonl に残る")


def cmd_answer(a):
    """人待ちへまとめて答える。工程役の問いへの答えも判断役の学習の材料として残す。"""
    p = pipeline()
    with locked():
        st = state()
        pend = {x["step"]: x for x in pending_list(st, p)}
        pairs = []
        for arg in a.pairs:
            if "=" not in arg:
                raise LoopError(f"{arg} は <工程>=<選択肢> の形ではありません")
            step, choice = arg.rsplit("=", 1)
            pairs.append((step, choice))
        if a.recommended:
            named = {s for s, _ in pairs}
            pairs += [(sid, "推奨") for sid, x in pend.items() if sid not in named and x.get("recommend")]
        if not pairs:
            raise LoopError("答える工程がありません（`pending`で一覧）")
        # 先に全部を確かめてから書く（途中で失敗して半分だけ反映されるのを避ける）
        plan = []
        for step, choice in pairs:
            x = pend.get(step)
            if x is None:
                raise LoopError(f"{step} は人待ちではありません（`pending`で一覧）")
            if x["kind"] == "blocked":
                raise LoopError(f"{step} は選択肢のある問いではありません。解けたら `unblock {step}`")
            if choice in ("推奨", "rec"):
                if not x.get("recommend"):
                    raise LoopError(f"{step} には推奨がありません。選択肢から選んでください: {' / '.join(x['options'])}")
                choice = x["recommend"]
            if choice not in x["options"]:
                raise LoopError(f"{step} の選択肢に {choice} はありません（{' / '.join(x['options'])}）")
            plan.append((step, choice, x))
        out = []
        for step, choice, x in plan:
            if x["kind"] == "judge":
                n = decide_core(st, p, step, choice, a.note)
                out.append(f"{step}: {choice} → {LABEL[st['steps'][step]['status']]}（正解{n}件）")
                continue
            s = st["steps"][step]
            ask = s.pop("ask")

            def label(r, jid=ask["jid"], choice=choice):
                if r.get("id") == jid:
                    r["human_answer"] = choice
                    r["note"] = a.note or ""
                    return True
                return False
            rewrite_judgments(label)
            s["status"], s["needs_human"], s["blocker"], s["shards"] = "in_progress", False, None, {}
            s.setdefault("answered", []).append({"question": ask["question"], "answer": choice, "note": a.note or ""})
            note(s, f"人の答え: {ask['question']} → {choice}" + (f"（{a.note}）" if a.note else ""))
            out.append(f"{step}: {choice} → 作業中（工程役へこの答えを渡して続ける）")
        save_json(STATE, st)
    print("\n".join(out))


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
        asks = [r for r in rows if r.get("kind") == "ask" and r.get("human_answer")][-a.lessons:]
        if asks:
            body += ["", "## 人の裁定（工程役が人に聞いた問いへの答え。同じ形の問いはこれに倣う）", ""]
            for r in asks:
                body.append(f"- 問い`{r['question']}`（工程{r['step']}）「{r.get('question_text', '')}」: 人の答えは`{r['human_answer']}`"
                            f"（選択肢 {' / '.join(r.get('options') or [])}・推奨は`{r.get('recommend')}`）。人の注記: {r.get('note', '')}")
        LESSONS.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"反映しました: {CALIBRATION.name}・{LESSONS.name}（誤りの例{len(wrong)}件・人の裁定{len(asks)}件）")
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
        elif r["status"] == "promoted":
            g = gate_stats().get((r["step"], r["id"]))
            need2 = p.get("sunset_min_runs", 10)
            if g and g["runs"] >= need2 and g["fails"] == 0:
                print(f"    → 採用後{g['runs']}回走って一度も落としていません。外す候補（`loopctl.py retire {r['id']}`）")
        elif r["status"] == "shadow" and s["fp"]:
            print(f"    → 誤検出があります。廃止するなら `loopctl.py retire {r['id']}`")


def set_rule_status(rid: str, status: str, force: bool = False) -> dict:
    rs = load_rules()
    for r in rs:
        if r["id"] == rid:
            if status == "promoted" and not force:
                cap = pipeline().get("judge", {}).get("max_promoted_per_step", 3)
                live = [x for x in rs if x["status"] == "promoted" and x["step"] == r["step"]]
                if len(live) >= cap:
                    raise LoopError(f"工程{r['step']}の採用中のルールが上限（{cap}本）です。1本足すなら1本見直す"
                                    f"（`loopctl.py gate-stats`で当たらないものを確かめて `retire`）。承知で足すなら --force")
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


# ---------- 検査ごとの打率と、外す候補（サンセット） ----------

LINE_RE = re.compile(r"^\s*(✔|✖)\s+(.*?)(?:\s*〔(.+)〕)?\s*$")


def record_gate_stats(run: str, step: str, out: str) -> None:
    """ゲートの出力を検査の鍵ごとに束ね、1回のゲートにつき1行ずつ記録する（鍵の無い行は本文を鍵にする）。"""
    agg: dict[str, bool] = {}
    for l in out.splitlines():
        m = LINE_RE.match(l)
        if not m:
            continue
        key = m.group(3) or m.group(2)
        agg[key] = agg.get(key, True) and m.group(1) == "✔"
    if not agg:
        return
    GATE_STATS.parent.mkdir(parents=True, exist_ok=True)
    with open(GATE_STATS, "a", encoding="utf-8") as fh:
        for k, ok in agg.items():
            fh.write(json.dumps({"t": now(), "run": run, "step": step, "key": k, "ok": ok}, ensure_ascii=False) + "\n")


def gate_stats() -> dict:
    st: dict[tuple, dict] = {}
    if not GATE_STATS.exists():
        return st
    for l in GATE_STATS.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        x = st.setdefault((r["step"], r["key"]), {"runs": 0, "fails": 0, "last_fail": None})
        x["runs"] += 1
        if not r["ok"]:
            x["fails"] += 1
            x["last_fail"] = r["t"]
    return st


def cmd_gate_stats(a):
    p = pipeline()
    need = p.get("sunset_min_runs", 10)
    stats = gate_stats()
    if not stats:
        print("ゲートの記録がまだありません")
        return
    print(f"{'工程':<14}{'実行':>5}{'不合格':>7}  検査")
    cands = []
    for (step, key), x in sorted(stats.items()):
        print(f"{step:<14}{x['runs']:>5}{x['fails']:>7}  {key}")
        if x["runs"] >= need and x["fails"] == 0:
            cands.append((step, key, x["runs"]))
    if cands:
        print(f"\n外す候補（{need}回以上走って一度も落ちていない）:")
        for step, key, n in cands:
            print(f"  - 工程{step}: {key}（{n}回）")
        print("  ※ 当たりゼロには「上流で捕れている」「見えていない」「抑止が効いている」の3通りがある。外すかは人が決める。"
              "ゲートのスクリプトから行を消す／昇格したルールなら `loopctl.py retire <id>`")


def cmd_accept_self(a):
    with locked():
        st = state()
        st["self_snapshot"] = self_snapshot()
        save_json(STATE, st)
    print("ループ自身のファイルの現状を、この実行の基準として控え直しました")


# ---------- その他の遷移 ----------

def cmd_block(a):
    """工程を止める。--ask で人に選んでもらう問いにすると、選択肢と推奨と人の答えが記録に残る。

    判断役の答え（--judge-answer / --confidence）を添え、その問いの閾値が較正で決まっていて届いていれば、
    止めずに判断役の答えで進める（人を減らしていく入口）。
    """
    if a.ask:
        if not a.options or len(a.options) < 2:
            raise LoopError("--ask には --options を2つ以上付けてください")
        for x, name in ((a.recommend, "--recommend"), (a.judge_answer, "--judge-answer")):
            if x is not None and x not in a.options:
                raise LoopError(f"{name} の {x} が選択肢（{' / '.join(a.options)}）にありません")
    elif a.options or a.recommend or a.judge_answer:
        raise LoopError("--options・--recommend・--judge-answer は --ask と一緒に使います")
    p = pipeline()
    cfg = p.get("judge", {})
    with locked():
        st = state()
        s = st_step(st, a.step)
        if not a.ask:
            s["status"] = "blocked"
            s["blocker"] = a.reason
            note(s, f"停止: {a.reason}")
            save_json(STATE, st)
            print(f"{a.step} を止めました: {a.reason}")
            return
        sd = step_def(p, a.step)
        qid = a.qid or f"ask:{sd.get('template', a.step)}"
        s["asks"] = s.get("asks", 0) + 1
        jid = f"{st['run_id']}-{a.step}-ask{s['asks']}"
        conf = float(a.confidence or 0)
        th = thresholds(p).get(qid)
        auto = (a.judge_answer is not None and th is not None and conf >= th
                and not audit_pick(jid, cfg.get("audit_rate", 0.0)))
        row = {"id": jid, "t": now(), "run": st["run_id"], "step": a.step, "kind": "ask", "question": qid,
               "question_text": a.ask, "options": a.options, "recommend": a.recommend, "reason": a.reason,
               "answer": a.judge_answer, "confidence": conf, "decision": "auto_answer" if auto else "escalate",
               "judge_reason": a.judge_reason or "", "human_answer": None, "note": ""}
        JUDGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(JUDGMENTS, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if auto:
            s.setdefault("answered", []).append({"question": a.ask, "answer": a.judge_answer, "note": "判断役"})
            note(s, f"判断役の答えで進める: {a.ask} → {a.judge_answer}（確信度{conf:.2f}≧{th:.2f}）")
            msg = (f"{a.step}: 判断役の答え {a.judge_answer} で進めます（確信度{conf:.2f}≧閾値{th:.2f}）。"
                   f"工程役へこの答えを渡して続ける。誤りなら `override {jid} <正しい答え>`")
        else:
            s["status"], s["needs_human"] = "blocked", True
            s["blocker"] = f"人に選んでもらう問い: {a.ask}"
            s["ask"] = {"jid": jid, "qid": qid, "question": a.ask, "options": a.options, "recommend": a.recommend,
                        "judge": {"answer": a.judge_answer, "confidence": conf, "reason": a.judge_reason or ""}
                        if a.judge_answer is not None else None}
            note(s, f"停止（人の選択待ち）: {a.ask}")
            msg = f"{a.step} を止めました（人の選択待ち）: {a.ask}。`loopctl.py pending` に並びます"
        save_json(STATE, st)
    print(msg)


def cmd_unblock(a):
    with locked():
        st = state()
        s = st_step(st, a.step)
        if s["status"] != "blocked":
            raise LoopError(f"{a.step} は止まっていません")
        s["status"] = "in_progress"
        s["blocker"] = None
        s["needs_human"] = False
        s.pop("ask", None)
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


def cmd_resume(a):
    p = pipeline()
    with locked():
        st = state()
        if a.extend:
            st["budget_extra"] = st.get("budget_extra", 0) + a.extend
        st["active"], st["finished"] = True, False
        st.pop("halted", None)
        st["stop_guard"] = {"count": 0, "fingerprint": ""}
        why = limit_reason(st, p)
        save_json(STATE, st)
    print("再開しました" + (f"（時間の予算を{a.extend}s延ばした。いま {effective_budget(st, p)}s）" if a.extend else ""))
    if why:
        print(f"※ まだ上限を超えています: {why}。次の着手でまた止まります"
              + ("（時間なら `resume --extend <秒>`）" if "時間" in why else "（pipeline.json の limits を見直す）"))


# ---------- 振り返り ----------

REWORK_KINDS = (("レビュー", "レビュー"), ("決定論ゲート不合格", "決定論ゲート"), ("判断役", "判断役"), ("人の判断", "人"))


def step_times(s: dict):
    """工程の着手（最初の「着手」の記録）と終わり（完了なら最後の記録）の時刻。"""
    ns = s.get("notes", [])
    start = next((n["t"] for n in ns if n["text"].startswith("着手")), None)
    end = ns[-1]["t"] if ns and s["status"] == "done" else None
    return start, end


def retro_data(st: dict, p: dict) -> dict:
    steps = st["steps"]
    end_t = st.get("finished_at") or now()
    rework_total = sum(s.get("rework", 0) for s in steps.values())
    kinds: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for s in steps.values():
        for n in s.get("notes", []):
            if not n["text"].startswith("差し戻し: "):
                continue
            body = n["text"][len("差し戻し: "):]
            kind = next((k for pre, k in REWORK_KINDS if body.startswith(pre)), "その他")
            kinds[kind] = kinds.get(kind, 0) + 1
            keys = re.findall(r"〔([^〕]+)〕", body)
            for k in keys or [body[:60]]:
                reasons[f"{kind}: {k}"] = reasons.get(f"{kind}: {k}", 0) + 1
    items = []
    for it in st.get("items", []):
        own = {sid: s for sid, s in steps.items() if sid.startswith(it + "/")}
        ts = [step_times(s) for s in own.values()]
        starts = [a for a, _ in ts if a]
        done = all(s["status"] == "done" for s in own.values()) and own
        ends = [b for _, b in ts if b]
        items.append({"item": it, "done": bool(done), "rework": sum(s.get("rework", 0) for s in own.values()),
                      "elapsed": int(max(ends) - min(starts)) if done and starts and ends else None,
                      "status": "完了" if done else next((LABEL[s["status"]] for s in own.values() if s["status"] != "done"), "未着手")})
    rows = [r for r in load_judgments() if r.get("run") == st["run_id"]]
    asks = [r for r in rows if r.get("kind") == "ask"]
    judged = [r for r in rows if r.get("kind") != "ask"]
    wrong = [r for r in rows if r.get("human_answer") and r.get("answer") is not None
             and r.get("decision") in ("auto_pass", "auto_fail", "auto_answer") and not correct(r)]
    return {
        "run": st["run_id"], "goal": st.get("goal", ""), "finished": bool(st.get("finished")),
        "elapsed": int(end_t - st["started_at"]),
        "steps_done": sum(1 for s in steps.values() if s["status"] == "done"), "steps_total": len(steps),
        "items": items,
        "rework_total": rework_total, "rework_by_kind": kinds,
        "rework_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:10],
        "nudges_total": st.get("nudges_total", 0),
        "human_waits": {"工程役の問い": len(asks),
                        "判断役が人へ回した": sum(1 for r in judged if r.get("decision") == "escalate"),
                        "理由だけの停止（いま）": sum(1 for s in steps.values()
                                             if s["status"] == "blocked" and not s.get("needs_human"))},
        "judge_wrong": len(wrong),
        "blocked_now": blocked_items(st),
    }


def cmd_retro(a):
    """実行の振り返りの数字（項目ごとの経過・差し戻しの理由の分布・催促・人待ち・判断役の誤り）。"""
    st, p = state(), pipeline()
    d = retro_data(st, p)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    out = [f"### {time.strftime('%Y-%m-%d', time.localtime(now()))} 振り返り（実行{d['run']}{'・閉じた' if d['finished'] else '・進行中'}）",
           f"- 経過 {d['elapsed']}s、工程 {d['steps_done']}/{d['steps_total']} 完了" + (f"。完了条件: {d['goal']}" if d["goal"] else "")]
    if d["items"]:
        done = [x for x in d["items"] if x["done"]]
        out.append(f"- 項目 {len(done)}/{len(d['items'])} 完了: " + "、".join(
            f"{x['item']}（{x['elapsed']}s・差し戻し{x['rework']}）" if x["done"] else f"{x['item']}（{x['status']}）" for x in d["items"]))
    out.append(f"- 差し戻し {d['rework_total']}回" + (f"（{'・'.join(f'{k}{v}' for k, v in d['rework_by_kind'].items())}）" if d["rework_by_kind"] else ""))
    for k, v in d["rework_reasons"]:
        out.append(f"  - {k}: {v}回")
    out.append(f"- Stopフックの催促 {d['nudges_total']}回")
    out.append("- 人待ち: " + "、".join(f"{k}{v}件" for k, v in d["human_waits"].items()))
    out.append(f"- 判断役が自動で決めて人が後から正した件数 {d['judge_wrong']}件（決定論ゲートの誤判定は数えられないので、気づいたら`[ひな型]`で1行）")
    if d["blocked_now"]:
        out.append("- いま止まっている: " + "、".join(d["blocked_now"]))
    print("\n".join(out))


def set_active(flag: bool, msg: str, finished: bool = False):
    with locked():
        st = state()
        st["active"] = flag
        st["finished"] = finished
        if finished:
            st["finished_at"] = now()
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
    b.add_argument("--items", nargs="*", help="項目ごとに回す時の項目id（pipeline.json の per_item.items より優先）")
    b.add_argument("--items-file", help="項目idの一覧（1行1件、またはJSONの配列）。無ければ pipeline.json の per_item.items_file")
    b.add_argument("--allow-empty", action="store_true", help="項目0件で始める（後から add-item する時）")
    b.add_argument("--limit", action="append", metavar="名前=値",
                   help="この実行の間だけ上限を差し替える（例 --limit max_shards=1。pipeline.json は書き換えない）")
    ai = sub.add_parser("add-item", help="実行中に項目を足す（per_item）"); ai.add_argument("items", nargs="*")
    ai.add_argument("--items-file")
    sh = sub.add_parser("show", help="工程の定義を出す（項目ごとの工程は展開後）"); sh.add_argument("step")
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
    sub.add_parser("gate-stats", help="検査ごとの打率と、外す候補")
    sub.add_parser("accept-self", help="人が直したループ自身のファイルを、この実行の基準として控え直す")
    pr = sub.add_parser("promote", help="ルールを決定論ゲートへ採用する（人が承認）"); pr.add_argument("rule_id"); pr.add_argument("--force", action="store_true")
    rt = sub.add_parser("retire", help="ルールを廃止する"); rt.add_argument("rule_id")
    bl = sub.add_parser("block"); bl.add_argument("step"); bl.add_argument("reason")
    bl.add_argument("--ask", help="人に選んでもらう問い"); bl.add_argument("--options", nargs="*", help="選択肢（2つ以上）")
    bl.add_argument("--recommend", help="推奨する選択肢"); bl.add_argument("--qid", help="問いの型のid（較正の単位。既定 ask:<工程の型>）")
    bl.add_argument("--judge-answer", help="判断役の答え"); bl.add_argument("--confidence", type=float, help="判断役の確信度")
    bl.add_argument("--judge-reason", help="判断役の根拠")
    pe = sub.add_parser("pending", help="人待ちの一覧（選択肢・推奨・判断役の答え）"); pe.add_argument("--json", action="store_true")
    an = sub.add_parser("answer", help="人待ちへまとめて答える"); an.add_argument("pairs", nargs="*", help="<工程>=<選択肢>（推奨どおりなら <工程>=推奨）")
    an.add_argument("--recommended", action="store_true", help="名指ししていない人待ちは、推奨どおりに答える"); an.add_argument("--note", default="")
    ub = sub.add_parser("unblock"); ub.add_argument("step"); ub.add_argument("--note", default="")
    ro = sub.add_parser("reopen"); ro.add_argument("step"); ro.add_argument("--note", default="")
    sub.add_parser("pause", help="Stopフックの催促を止める（人が付き添う時）")
    rs = sub.add_parser("resume", help="催促を再開する（止まっていた実行も）"); rs.add_argument("--extend", type=int, default=0, help="時間の予算をこの秒数だけ延ばす")
    sub.add_parser("finish", help="実行を閉じる")
    rr = sub.add_parser("retro", help="振り返りの数字（candidates.md の振り返り節へ貼る）"); rr.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        {
            "begin": cmd_begin, "status": cmd_status, "next": cmd_next, "start": cmd_start, "submit": cmd_submit,
            "review": cmd_review, "gate": cmd_gate, "judge": cmd_judge, "decide": cmd_decide, "override": cmd_override,
            "calibrate": cmd_calibrate, "rules": cmd_rules, "promote": cmd_promote, "retire": cmd_retire,
            "gate-stats": cmd_gate_stats, "accept-self": cmd_accept_self, "block": cmd_block, "unblock": cmd_unblock, "reopen": cmd_reopen,
            "add-item": cmd_add_item, "show": cmd_show, "pending": cmd_pending, "answer": cmd_answer, "retro": cmd_retro,
            "pause": lambda a: set_active(False, "一時停止しました（Stopフックは催促しません）"),
            "resume": cmd_resume,
            "finish": lambda a: set_active(False, "実行を閉じました", finished=True),
        }[a.cmd](a)
    except LoopError as e:
        print(f"loopctl: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
