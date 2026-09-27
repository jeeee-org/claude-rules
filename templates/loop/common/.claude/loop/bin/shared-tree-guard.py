#!/usr/bin/env python3
"""PreToolUseフック（Bash）: ループの実行中、工程役・レビュー役が共有の作業ツリーを巻き戻す git を止める。

直列の工程では、作業ツリーの未コミットの変更がその工程の唯一の成果物になる。工程役が変異テストの途中で
`git checkout`して成果物を消した・レビュー役が比べるために`git stash`した例がある（mtg-practice）。
消えると気づかれずに提出されうるので、次を止める:

    git checkout / switch / stash（list・show は除く） / reset / restore（--staged だけは除く） / clean

止めるのは、そのコマンドがこのリポの作業ツリー（同じトップレベル）に向く時だけ。`git worktree add`した
別の場所や写しでの`git -C <別の場所> checkout`は通す（壊して試す・前と比べるのはそちらでする）。
効くのはループの実行中（一時停止中を含む）の、ループのサブエージェント（pipeline.jsonの工程役・レビュー役・
判断役）だけ。統括役と人のセッションには口を出さない。
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loopctl as lc  # noqa: E402

SEPS = {"&&", "||", ";", "|", "&", "\n", "(", ")"}
NO_ARG_OPTS = {"--no-pager", "-p", "--paginate", "--bare", "--no-replace-objects", "--literal-pathspecs"}


def toplevel(d: Path) -> Path | None:
    if not d.is_dir():
        return None
    r = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None


def segments(cmd: str):
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    seg = []
    for t in lex:
        if t in SEPS or set(t) <= set(";&|()"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def risky(args: list[str]) -> tuple[str, list[str]] | None:
    """git の後ろの引数から（-C の行き先, サブコマンド）を読み、巻き戻す操作ならそれを返す。"""
    dirs, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            dirs.append(args[i + 1]); i += 2; continue
        if a.startswith(("--git-dir", "--work-tree")):
            return None  # 別の場所を明示している
        if a == "-c" and i + 1 < len(args):
            i += 2; continue
        if a in NO_ARG_OPTS or a.startswith("--"):
            i += 1; continue
        break
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub in ("checkout", "switch", "reset", "clean"):
        return sub, dirs
    if sub == "stash" and not (rest and rest[0] in ("list", "show")):
        return sub, dirs
    if sub == "restore":
        staged_only = ("--staged" in rest or "-S" in rest) and not ("--worktree" in rest or "-W" in rest)
        return None if staged_only else (sub, dirs)
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        p = lc.pipeline()
    except Exception:
        return 0
    st = lc.load_json(lc.STATE)
    if not st or st.get("finished"):
        return 0
    if (data.get("agent_type") or "") not in lc.loop_agents(p):
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "git" not in cmd:
        return 0
    repo = toplevel(lc.REPO) or lc.REPO.resolve()
    cwd = Path(data.get("cwd") or os.getcwd())
    try:
        segs = list(segments(cmd))
    except ValueError:
        return 0
    for seg in segs:
        while seg and "=" in seg[0] and not seg[0].startswith("="):
            seg = seg[1:]  # VAR=値 の前置き
        if not seg:
            continue
        if seg[0] == "cd":
            cwd = (cwd / os.path.expanduser(seg[1])) if len(seg) > 1 else Path.home()
            continue
        if Path(seg[0]).name != "git":
            continue
        hit = risky(seg[1:])
        if not hit:
            continue
        sub, dirs = hit
        d = cwd
        for x in dirs:
            d = d / os.path.expanduser(x)
        if toplevel(d) != repo:
            continue
        reason = (f"ループの実行中は、共有の作業ツリーで `git {sub}` をしない（未コミットの変更がこの工程の成果物で、"
                  "消えると気づかれずに提出されうる）。壊して試す・前と比べる時は作業ツリーの外で: "
                  "`git worktree add <外の場所> HEAD` した場所か写しで行い、比べるだけなら `git diff` / `git show <版>:<パス>` を使う。"
                  "どうしても要るなら `STATUS: blocked` で統括役へ返す")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
