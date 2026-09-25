#!/usr/bin/env python3
"""ループ系エージェントのひな型を、対象のリポへ入れる。

    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --profile dev|generic [--dry-run] [--force] [--no-settings]

- ひな型は templates/loop/common と templates/loop/<profile> を重ねたもの
- 既にあるファイルは上書きしない（--force で上書き）。入れた後の微調整は対象リポで行う前提
- 対象の .claude/settings.json に Stop / SubagentStop フックを足す（同じコマンドがあれば足さない。控えは .bak）
- 何をどこから入れたかを .claude/loop/.scaffold.json に残す（後でひな型との差分を見るため）
- commitはしない
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TEMPLATES = SRC / "templates" / "loop"
PROFILES = ("dev", "generic")

HOOKS = {
    "Stop": 'python3 "${CLAUDE_PROJECT_DIR}/.claude/loop/bin/stop-guard.py"',
    "SubagentStop": 'python3 "${CLAUDE_PROJECT_DIR}/.claude/loop/bin/subagent-report-guard.py"',
}


def plan(profile: str) -> dict[Path, Path]:
    """公開先の相対パス → ひな型の実ファイル。profile側が同じパスを持てばcommonを上書きする。"""
    files: dict[Path, Path] = {}
    for layer in ("common", profile):
        root = TEMPLATES / layer
        for f in sorted(root.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                files[f.relative_to(root)] = f
    return files


def source_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def merge_settings(path: Path, dry: bool) -> list[str]:
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"loop-scaffold: {path} をJSONとして読めません（{e}）。手で直してから再実行してください")
    added = []
    hooks = data.setdefault("hooks", {})
    for event, cmd in HOOKS.items():
        groups = hooks.setdefault(event, [])
        present = any(h.get("command") == cmd for g in groups for h in g.get("hooks", []))
        if not present:
            groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
            added.append(event)
    if added and not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ループ系エージェントのひな型を対象リポへ入れる")
    ap.add_argument("target", help="対象リポのルート")
    ap.add_argument("--profile", required=True, choices=PROFILES, help="dev=要件→設計→実装→テスト / generic=工程を自分で決める")
    ap.add_argument("--dry-run", action="store_true", help="何が起きるかだけを出す")
    ap.add_argument("--force", action="store_true", help="既にあるファイルも上書きする")
    ap.add_argument("--no-settings", action="store_true", help=".claude/settings.json にフックを足さない")
    a = ap.parse_args(argv)

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"loop-scaffold: {target} はディレクトリではありません", file=sys.stderr)
        return 2
    if (target / ".git").exists() is False:
        print(f"※ {target} はgitリポのルートではないようです（続けます）", file=sys.stderr)

    created, skipped, overwritten = [], [], []
    for rel, src in plan(a.profile).items():
        dst = target / rel
        if dst.exists() and not a.force:
            skipped.append(rel)
            continue
        (overwritten if dst.exists() else created).append(rel)
        if not a.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst.suffix in (".py", ".sh"):
                dst.chmod(0o755)

    added = [] if a.no_settings else merge_settings(target / ".claude" / "settings.json", a.dry_run)

    if not a.dry_run:
        meta = target / ".claude" / "loop" / ".scaffold.json"
        meta.write_text(json.dumps({"source": "claude-rules/templates/loop", "rev": source_rev(), "profile": a.profile,
                                    "at": time.strftime("%Y-%m-%d")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    head = "（確認だけ・何も書いていません）" if a.dry_run else ""
    print(f"ループのひな型（{a.profile}）→ {target} {head}")
    for label, xs in (("作成", created), ("上書き", overwritten), ("既にあるので省略", skipped)):
        if xs:
            print(f"  {label}: {len(xs)}件")
            for x in xs:
                print(f"    {x}")
    if a.no_settings:
        print("  settings.json: 触っていません（--no-settings）。フックを使うなら手で足してください")
    elif added:
        print(f"  settings.json: {', '.join(added)} フックを足しました")
    else:
        print("  settings.json: フックは登録済み")
    if not a.dry_run:
        print("\n次にやること（詳しくは .claude/loop/README.md）:")
        print("  1. .claude/loop/GOAL.md に完了条件を書く")
        print("  2. .claude/loop/gates/commands.env にビルド・リント・テストのコマンドを書く")
        print("  3. .claude/loop/pipeline.json の工程をこのリポに合わせる")
        print("  4. claude --agent loop-conductor で回す")
    return 0


if __name__ == "__main__":
    sys.exit(main())
