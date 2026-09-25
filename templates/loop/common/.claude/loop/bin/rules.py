"""判断役から昇格させる決定論ルール（loopctl.pyから使う）。

ルールは「この検査に落ちたら、その問いの答えは不合格」という**不合格の検出器**だけ。
検査は下の4種の組み合わせに限る（判断役に自由なコードを書かせないため。安全で、機械で検証できる）。

    {"kind": "need_file",    "args": ["<パス>"]}
    {"kind": "need_match",   "args": ["<パス>", "<正規表現>"]}
    {"kind": "forbid_match", "args": ["<パス>", "<正規表現>"]}
    {"kind": "need_all_ids", "args": ["<元パス>", "<先パス>", "<idの正規表現>"]}

パスはリポのルートからの相対パス。リポの外（絶対パス・..）は拒む。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

KINDS = {"need_file": 1, "need_match": 2, "forbid_match": 2, "need_all_ids": 3}
PATH_ARGS = {"need_file": (0,), "need_match": (0,), "forbid_match": (0,), "need_all_ids": (0, 1)}
REGEX_ARGS = {"need_match": (1,), "forbid_match": (1,), "need_all_ids": (2,)}


def validate(check) -> str | None:
    """検査の形が正しければNone、誤りなら理由。"""
    if not isinstance(check, dict) or check.get("kind") not in KINDS:
        return f"kind は {', '.join(KINDS)} のどれか"
    args = check.get("args")
    if not isinstance(args, list) or len(args) != KINDS[check["kind"]] or not all(isinstance(x, str) and x for x in args):
        return f"{check['kind']} の args は文字列{KINDS[check['kind']]}個"
    for i in PATH_ARGS[check["kind"]]:
        p = Path(args[i])
        if p.is_absolute() or ".." in p.parts:
            return f"リポの外のパスは使えない: {args[i]}"
    for i in REGEX_ARGS[check["kind"]]:
        try:
            re.compile(args[i])
        except re.error as e:
            return f"正規表現が不正: {args[i]}（{e}）"
    if check["kind"] == "need_all_ids" and re.compile(args[2]).groups:
        return "idの正規表現に捕獲の括弧は使えない（(?:…)にする）"
    return None


def rule_id(question: str, check: dict) -> str:
    key = json.dumps({"q": question, "c": check}, sort_keys=True, ensure_ascii=False)
    return "r-" + hashlib.sha256(key.encode()).hexdigest()[:8]


def describe(check: dict) -> str:
    k, a = check["kind"], check["args"]
    return {
        "need_file": lambda: f"{a[0]} がある",
        "need_match": lambda: f"{a[0]} に /{a[1]}/ がある",
        "forbid_match": lambda: f"{a[0]} に /{a[1]}/ が無い",
        "need_all_ids": lambda: f"{a[0]} の /{a[2]}/ のidが {a[1]} にすべてある",
    }[k]()


def _read(repo: Path, rel: str) -> str | None:
    try:
        return (repo / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def evaluate(check: dict, repo: Path) -> tuple[bool, str]:
    """検査を回す。(通ったか, 1行の説明)。通らない＝ルールが不合格を検出した。"""
    k, a = check["kind"], check["args"]
    if k == "need_file":
        t = _read(repo, a[0])
        return bool(t and t.strip()), f"{a[0]} が" + ("ある" if t and t.strip() else "無いか空")
    if k in ("need_match", "forbid_match"):
        t = _read(repo, a[0])
        hit = t is not None and re.search(a[1], t, re.M) is not None
        if k == "need_match":
            return hit, f"{a[0]} に /{a[1]}/ が" + ("ある" if hit else "無い")
        return (not hit), f"{a[0]} に /{a[1]}/ が" + ("ある" if hit else "無い")
    src, dst = _read(repo, a[0]), _read(repo, a[1])
    if src is None or dst is None:
        return False, f"{a[0]} か {a[1]} が読めない"
    missing = sorted(i for i in set(re.findall(a[2], src)) if i not in dst)
    return (not missing), (f"{a[1]} に無いid: {' '.join(missing)}" if missing else f"{a[1]} に全idがある")
