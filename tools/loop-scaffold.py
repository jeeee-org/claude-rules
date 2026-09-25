#!/usr/bin/env python3
"""ループ系エージェントのひな型を、対象のリポへ入れる。

    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --profile dev|generic [--dry-run] [--force] [--no-settings] [--enable-todo]
    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --update [--dry-run]   # 入れた先を新しい版へ

- ひな型は templates/loop/common と templates/loop/<profile> を重ねたもの
- 既にあるファイルは上書きしない（--force で上書き）。入れた後の微調整は対象リポで行う前提
- 対象の .claude/settings.json に Stop / SubagentStop フックを足す（同じコマンドがあれば足さない。控えは .bak）
- --enable-todo で、そのリポだけto-doツール（CLAUDE_CODE_ENABLE_TODO_TOOLS=1）を有効にする（全体では無効のまま）
- 何をどこから入れたかを .claude/loop/.scaffold.json に残す（後でひな型との差分を見るため）
- --update は .claude/loop/.scaffold.json の版（入れた時の版）と突き合わせて更新する。
  無いファイルは作り、入れた時の版のまま（手を入れていない）のファイルは新しい版で上書きし、
  手で直されたファイルは触らずに一覧と取り込み用の差分コマンドを出す
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


def old_template(rev: str, src: Path, old_dir: Path | None) -> bytes | None:
    """入れた時の版のひな型の中身。--old-dir（その版の templates/loop）があればそこから、無ければgitの履歴から。"""
    rel = src.relative_to(TEMPLATES)
    if old_dir is not None:
        f = old_dir / rel
        return f.read_bytes() if f.exists() else None
    r = subprocess.run(["git", "-C", str(SRC), "show", f"{rev}:templates/loop/{rel.as_posix()}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def update(target: Path, dry: bool, old_dir: Path | None) -> int:
    meta_p = target / ".claude" / "loop" / ".scaffold.json"
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"loop-scaffold: {meta_p} が読めません（ひな型を入れたリポではないか、入れた記録が無い）", file=sys.stderr)
        return 2
    profile, rev = meta["profile"], meta["rev"]
    new_rev = source_rev()
    created, updated, same, manual = [], [], [], []
    for rel, src in plan(profile).items():
        dst = target / rel
        new = src.read_bytes()
        if not dst.exists():
            created.append(rel)
        elif dst.read_bytes() == new:
            same.append(rel)
            continue
        else:
            old = old_template(rev, src, old_dir)
            if old is not None and dst.read_bytes() == old:
                updated.append(rel)
            else:
                manual.append((rel, src))
                continue
        if not dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst.suffix in (".py", ".sh"):
                dst.chmod(0o755)
    added = merge_settings(target / ".claude" / "settings.json", dry)
    if not dry:
        meta.update({"rev": new_rev, "updated_from": rev, "at": time.strftime("%Y-%m-%d")})
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    head = "（確認だけ・何も書いていません）" if dry else ""
    print(f"ループのひな型を更新（{profile}、{rev} → {new_rev}）→ {target} {head}")
    for label, xs in (("作成（新しく増えたファイル）", created), ("上書き（手を入れていなかったファイル）", updated)):
        if xs:
            print(f"  {label}: {len(xs)}件")
            for x in xs:
                print(f"    {x}")
    print(f"  変わりなし: {len(same)}件")
    if added:
        print(f"  settings.json: {', '.join(added)} を足しました")
    if manual:
        print(f"  **手で直されているので触っていない: {len(manual)}件**。ひな型側の変更を見て、手で取り込む:")
        for rel, src in manual:
            print(f"    {rel}")
            print(f"      git -C {SRC} diff {rev} {new_rev} -- templates/loop/{src.relative_to(TEMPLATES).as_posix()}")
    if not dry:
        print("\n実行中のループがあれば、`loopctl.py finish` してから `begin` し直す（新しい状態の項目は begin で作られる）")
    return 0


def source_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def merge_settings(path: Path, dry: bool, hooks_on: bool = True, todo: bool = False) -> list[str]:
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"loop-scaffold: {path} をJSONとして読めません（{e}）。手で直してから再実行してください")
    added = []
    if todo and data.get("env", {}).get("CLAUDE_CODE_ENABLE_TODO_TOOLS") != "1":
        data.setdefault("env", {})["CLAUDE_CODE_ENABLE_TODO_TOOLS"] = "1"
        added.append("env.CLAUDE_CODE_ENABLE_TODO_TOOLS")
    hooks = data.setdefault("hooks", {}) if hooks_on else {}
    for event, cmd in (HOOKS.items() if hooks_on else ()):
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
    ap.add_argument("--profile", choices=PROFILES, help="dev=要件→設計→実装→テスト / generic=工程を自分で決める（新規に入れる時は必須）")
    ap.add_argument("--update", action="store_true", help="入れた先を新しい版へ（手で直したファイルは触らない）")
    ap.add_argument("--old-dir", type=Path, help=argparse.SUPPRESS)  # テスト用: 入れた時の版の templates/loop
    ap.add_argument("--dry-run", action="store_true", help="何が起きるかだけを出す")
    ap.add_argument("--force", action="store_true", help="既にあるファイルも上書きする")
    ap.add_argument("--no-settings", action="store_true", help=".claude/settings.json にフックを足さない")
    ap.add_argument("--enable-todo", action="store_true", help="このリポだけto-doツールを有効にする（settings.jsonのenv）")
    a = ap.parse_args(argv)

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"loop-scaffold: {target} はディレクトリではありません", file=sys.stderr)
        return 2
    if a.update:
        return update(target, a.dry_run, a.old_dir)
    if not a.profile:
        ap.error("新規に入れる時は --profile dev か --profile generic を指定してください（入れた先の更新なら --update）")
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

    settings = target / ".claude" / "settings.json"
    added = merge_settings(settings, a.dry_run, hooks_on=not a.no_settings, todo=a.enable_todo) \
        if (not a.no_settings or a.enable_todo) else []

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
    if a.no_settings and not added:
        print("  settings.json: 触っていません（--no-settings）。フックを使うなら手で足してください")
    elif added:
        print(f"  settings.json: {', '.join(added)} を足しました")
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
