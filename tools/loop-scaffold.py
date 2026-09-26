#!/usr/bin/env python3
"""ループ系エージェントのひな型を、対象のリポへ入れる。

    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --profile dev|generic [--dry-run] [--force] [--no-settings] [--enable-todo]
    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --update [--dry-run]   # 入れた先を新しい版へ
    python3 <claude-rules>/tools/loop-scaffold.py <対象リポ> --profile generic --name <名前>  # 同じリポに2つ目のループ

- ひな型は templates/loop/common と templates/loop/<profile> を重ねたもの
- 既にあるファイルは上書きしない（--force で上書き）。入れた後の微調整は対象リポで行う前提
- 対象の .claude/settings.json に Stop / SubagentStop フックを足す（同じコマンドがあれば足さない。控えは .bak）
- --enable-todo で、そのリポだけto-doツール（CLAUDE_CODE_ENABLE_TODO_TOOLS=1）を有効にする（全体では無効のまま）
- 何をどこから入れたかを .claude/loop/.scaffold.json に残す（後でひな型との差分を見るため）
- --update は .claude/loop/.scaffold.json の版（入れた時の版）と突き合わせて更新する。
  無いファイルは作り、入れた時の版のまま（手を入れていない）のファイルは新しい版で上書きし、
  手で直されたファイルは触らずに一覧と取り込み用の差分コマンドを出す
- 登録先の settings.json やひな型の要のファイルが git の無視対象なら知らせる（そのworktreeにしか無い）
- --name <名前> で、ループの置き場を .claude/loop-<名前>/ に、エージェントを <名前>-<元の名前> にして入れる
  （中身の参照も付け替える）。同じリポに2つ目のループを置くため。--update にも同じ --name を渡す
- commitはしない
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TEMPLATES = SRC / "templates" / "loop"
PROFILES = ("dev", "generic")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# 境目は英数字と - _ だけで見る（\w は日本語も含むので「gate-judgeを」の境目を見落とす）
EDGE_L, EDGE_R = r"(?<![A-Za-z0-9_-])", r"(?![A-Za-z0-9_-])"


def plan(profile: str) -> dict[Path, Path]:
    """公開先の相対パス → ひな型の実ファイル。profile側が同じパスを持てばcommonを上書きする。"""
    files: dict[Path, Path] = {}
    for layer in ("common", profile):
        root = TEMPLATES / layer
        for f in sorted(root.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                files[f.relative_to(root)] = f
    return files


class Naming:
    """同じリポに2つ目以降のループを置くための名前の付け替え（--name）。名前が無ければ何も変えない。"""

    def __init__(self, name: str | None, profile: str):
        self.name = name or None
        self.agents = sorted({src.stem for rel, src in plan(profile).items() if rel.parts[:2] == (".claude", "agents")},
                             key=len, reverse=True)
        self.loop_rel = Path(".claude") / (f"loop-{name}" if name else "loop")

    def agent(self, a: str) -> str:
        return f"{self.name}-{a}" if self.name else a

    def path(self, rel: Path) -> Path:
        if not self.name:
            return rel
        if rel.parts[:2] == (".claude", "loop"):
            return self.loop_rel.joinpath(*rel.parts[2:])
        if rel.parts[:2] == (".claude", "agents"):
            return Path(".claude", "agents", self.agent(rel.stem) + rel.suffix)
        return rel

    def content(self, data: bytes) -> bytes:
        if not self.name:
            return data
        try:
            t = data.decode("utf-8")
        except UnicodeDecodeError:
            return data
        t = re.sub(r"\.claude/loop" + EDGE_R, f".claude/loop-{self.name}", t)
        for a in self.agents:
            t = re.sub(EDGE_L + re.escape(a) + EDGE_R, self.agent(a), t)
        return t.encode("utf-8")

    def hooks(self) -> dict[str, str]:
        d = self.loop_rel.as_posix()
        return {"Stop": f'python3 "${{CLAUDE_PROJECT_DIR}}/{d}/bin/stop-guard.py"',
                "SubagentStop": f'python3 "${{CLAUDE_PROJECT_DIR}}/{d}/bin/subagent-report-guard.py"'}

    def shared(self) -> tuple[str, ...]:
        # git の無視対象だと、フックやループの定義がそのworktreeにしか無い（他のworktree・cloneでは効かない）
        return (".claude/settings.json", f".claude/agents/{self.agent('loop-conductor')}.md",
                f"{self.loop_rel.as_posix()}/pipeline.json")


def put(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    if dst.suffix in (".py", ".sh"):
        dst.chmod(0o755)


def old_template(rev: str, src: Path, old_dir: Path | None) -> bytes | None:
    """入れた時の版のひな型の中身。--old-dir（その版の templates/loop）があればそこから、無ければgitの履歴から。"""
    rel = src.relative_to(TEMPLATES)
    if old_dir is not None:
        f = old_dir / rel
        return f.read_bytes() if f.exists() else None
    r = subprocess.run(["git", "-C", str(SRC), "show", f"{rev}:templates/loop/{rel.as_posix()}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def update(target: Path, dry: bool, old_dir: Path | None, name: str | None = None) -> int:
    meta_p = target / ".claude" / (f"loop-{name}" if name else "loop") / ".scaffold.json"
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        others = sorted(p.parent.name for p in (target / ".claude").glob("loop-*/.scaffold.json"))
        hint = f"。名前を付けて入れたループなら --name（あるのは {', '.join(x[5:] for x in others)}）" if others and not name else ""
        print(f"loop-scaffold: {meta_p} が読めません（ひな型を入れたリポではないか、入れた記録が無い）{hint}", file=sys.stderr)
        return 2
    profile, rev = meta["profile"], meta["rev"]
    nm = Naming(meta.get("name"), profile)
    new_rev = source_rev()
    created, updated, same, manual, kept = [], [], [], [], []
    for rel0, src in plan(profile).items():
        rel = nm.path(rel0)
        dst = target / rel
        new = nm.content(src.read_bytes())
        if not dst.exists():
            created.append(rel)
        elif dst.read_bytes() == new:
            same.append(rel)
            continue
        else:
            old = old_template(rev, src, old_dir)
            if old is not None and dst.read_bytes() == nm.content(old):
                updated.append(rel)
            elif old is not None and nm.content(old) == new:
                kept.append(rel)  # 手を入れてあるが、ひな型側はこの間に変わっていない（取り込むものが無い）
                continue
            else:
                manual.append((rel, src))
                continue
        if not dry:
            put(dst, new)
    added = merge_settings(target / ".claude" / "settings.json", dry, hooks=nm.hooks())
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
    if kept:
        print(f"  手を入れてある（ひな型側の変更なし・取り込むものは無い）: {len(kept)}件: " + ", ".join(str(x) for x in kept))
    if added:
        print(f"  settings.json: {', '.join(added)} を足しました")
    if manual:
        print(f"  **手で直されているので触っていない: {len(manual)}件**。ひな型側の変更を見て、手で取り込む:")
        for rel, src in manual:
            print(f"    {rel}")
            print(f"      git -C {SRC} diff {rev} {new_rev} -- templates/loop/{src.relative_to(TEMPLATES).as_posix()}")
    if not dry:
        print("\n実行中のループがあれば、`loopctl.py finish` してから `begin` し直す（新しい状態の項目は begin で作られる）")
    warn_ignored(target, nm)
    warn_linters(target)
    return 0


def source_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def merge_settings(path: Path, dry: bool, hooks_on: bool = True, todo: bool = False,
                   hooks: dict[str, str] | None = None) -> list[str]:
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
    reg = data.setdefault("hooks", {}) if hooks_on else {}
    for event, cmd in ((hooks or Naming(None, "dev").hooks()).items() if hooks_on else ()):
        groups = reg.setdefault(event, [])
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


def ignored_paths(target: Path, nm: Naming) -> list[str]:
    """設定・統括役・工程表のうち git の無視対象になっているもの。gitリポでなければ空。"""
    try:
        r = subprocess.run(["git", "-C", str(target), "check-ignore", "--no-index", *nm.shared()],
                           capture_output=True, text=True)
    except OSError:
        return []
    if r.returncode not in (0, 1):  # 128 = gitリポでない等
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def warn_ignored(target: Path, nm: Naming) -> None:
    ignored = ignored_paths(target, nm)
    if ignored:
        print(f"\n※ 次のファイルがgitの無視対象です: {', '.join(ignored)}")
        print("  フック・ループの定義・実行中の状態は、このworktreeにしか無い。")
        print("  ループはこのworktreeから起動し、終わってもworktreeを消さない（他のworktreeやcloneでは効かない）")


# 入れた先のリンタ設定。ひな型のPython・シェルはリポのリンタ設定に合わせて書いていないので、対象から外してもらう
LINTERS = (
    ("pyproject.toml", ("[tool.ruff", "[tool.flake8", "[tool.pylint"), "ruff: [tool.ruff] に extend-exclude = [\".claude\"]"),
    ("ruff.toml", ("",), "ruff: extend-exclude = [\".claude\"]"),
    (".ruff.toml", ("",), "ruff: extend-exclude = [\".claude\"]"),
    (".flake8", ("",), "flake8: extend-exclude = .claude"),
    ("setup.cfg", ("[flake8]",), "flake8: [flake8] に extend-exclude = .claude"),
    ("tox.ini", ("[flake8]",), "flake8: [flake8] に extend-exclude = .claude"),
    ("eslint.config.js", ("",), "eslint: ignores に \".claude/**\""),
    ("eslint.config.mjs", ("",), "eslint: ignores に \".claude/**\""),
    (".eslintrc.json", ("",), "eslint: ignorePatterns に \".claude/\""),
    (".eslintrc.js", ("",), "eslint: ignorePatterns に \".claude/\""),
    ("biome.json", ("",), "biome: files.ignore に \".claude\""),
)


def linter_hints(target: Path) -> list[str]:
    """入れた先にリンタの設定があり、まだ .claude を外していなければ、その外し方。"""
    out = []
    for name, marks, hint in LINTERS:
        f = target / name
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if any(m in text for m in marks) and ".claude" not in text:
            out.append(f"{name}（{hint}）")
    return out


def warn_linters(target: Path) -> None:
    hints = linter_hints(target)
    if hints:
        print("\n※ リンタの設定があります。ひな型（.claude/ の下のPython・シェル）はこのリポのリンタ設定に合わせて"
              "書いていないので、工程役に「リンタを通す」と指示すると毎回落ちます。対象から .claude を外してください:")
        for h in hints:
            print(f"  - {h}")


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
    ap.add_argument("--name", help="2つ目以降のループの名前（置き場 .claude/loop-<名前>/・エージェント <名前>-…）")
    a = ap.parse_args(argv)
    if a.name is not None and not NAME_RE.match(a.name):
        ap.error("--name は英小文字・数字・- だけ（先頭は英小文字か数字）")

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"loop-scaffold: {target} はディレクトリではありません", file=sys.stderr)
        return 2
    if a.update:
        return update(target, a.dry_run, a.old_dir, a.name)
    if not a.profile:
        ap.error("新規に入れる時は --profile dev か --profile generic を指定してください（入れた先の更新なら --update）")
    if (target / ".git").exists() is False:
        print(f"※ {target} はgitリポのルートではないようです（続けます）", file=sys.stderr)

    nm = Naming(a.name, a.profile)
    created, skipped, overwritten = [], [], []
    for rel0, src in plan(a.profile).items():
        rel = nm.path(rel0)
        dst = target / rel
        if dst.exists() and not a.force:
            skipped.append(rel)
            continue
        (overwritten if dst.exists() else created).append(rel)
        if not a.dry_run:
            put(dst, nm.content(src.read_bytes()))

    settings = target / ".claude" / "settings.json"
    added = merge_settings(settings, a.dry_run, hooks_on=not a.no_settings, todo=a.enable_todo, hooks=nm.hooks()) \
        if (not a.no_settings or a.enable_todo) else []

    if not a.dry_run:
        meta = target / nm.loop_rel / ".scaffold.json"
        info = {"source": "claude-rules/templates/loop", "rev": source_rev(), "profile": a.profile,
                "at": time.strftime("%Y-%m-%d")}
        if a.name:
            info["name"] = a.name
        meta.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
        d = nm.loop_rel.as_posix()
        print(f"\n次にやること（詳しくは {d}/README.md）:")
        print(f"  1. {d}/GOAL.md に完了条件を書く")
        print(f"  2. {d}/gates/commands.env にビルド・リント・テストのコマンドを書く")
        print(f"  3. {d}/pipeline.json の工程をこのリポに合わせる")
        print(f"  4. claude --agent {nm.agent('loop-conductor')} で回す（--agent で起動しないとStopフックの早止まり対策は効かない）")
    warn_ignored(target, nm)
    warn_linters(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
