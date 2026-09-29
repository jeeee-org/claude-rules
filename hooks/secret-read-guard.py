#!/usr/bin/env python3
"""secret-read-guard.py — PreToolUse（Bash / Read / Grep）フック

資格情報を持つファイル（~/.claude.json・~/.aws/credentials・.env など）を**丸ごと出力する読み方**を止める。
出力はモデルへの入力と会話の記録に残り、消せない。レビュー役が ~/.claude.json を cat して、
APIトークンの値がツール出力に載ったことがある（IMPROVEMENTS 2026-09-29。トークンは作り直した）。

止めるもの:
  - Read: 資格情報のファイルを読む（Readは中身を丸ごと返す）
  - Grep: 資格情報のファイルに対して、合う行を出す読み方（output_mode=content）
  - Bash: 資格情報のファイルの名前と、中身を出す道具（cat・head・less・jq・python など）が同じ呼び出しにある
通すもの:
  - キーの有無・件数だけを返す読み方: `jq 'keys'`・`jq 'has("x")'`・`jq 'length'`・`grep -c`・`grep -q`・`grep -l`
  - 中身を出さない道具だけの呼び出し: ls・stat・test・wc など
  - コマンドの先頭に CR_SKIP_SECRET_GUARD=1 を付けたもの（人が中身を見てよいと決めた時の脱出弁）

fail-open: 入力が読めない時は黙って通す。
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")

# 資格情報を持つファイル（~ は展開した形で照合する）
SECRET_PATTERNS = [
    r"~/\.claude\.json(\.backup[^/\s]*)?",
    r"~/\.claude/\.credentials\.json",
    r"~/\.codex/auth\.json",
    r"~/\.aws/credentials",
    r"~/\.aws/(sso|cli)/cache/[^\s'\"]*",
    r"~/\.config/gh/hosts\.yml",
    r"~/\.config/gcloud/(credentials\.db|access_tokens\.db|application_default_credentials\.json|legacy_credentials/[^\s'\"]*)",
    r"~/\.netrc",
    r"~/\.git-credentials",
    r"~/\.docker/config\.json",
    r"~/\.npmrc",
    r"~/\.pypirc",
    r"~/\.kube/config",
    r"~/\.ssh/id_[A-Za-z0-9_]+(?!\.pub)\b",
]
# PJの .env / .env.local など（例示用の .env.example 等は除く）
DOTENV_RE = re.compile(r"(^|[\s/'\"=])\.env(\.(?!example|sample|template|dist|defaults)[A-Za-z0-9_-]+)?(?=$|[\s'\";|&)<>])")

# 中身を出す道具（呼び出しの先頭の語で見る。git commit のメッセージに「cat .env」と書いても止めない）。
# キーだけを返す jq の読み方と grep -c/-q/-l は別に通す
DUMP_CMDS = {"cat", "less", "more", "head", "tail", "bat", "batcat", "nl", "tac", "strings", "xxd", "od", "hexdump",
             "base64", "vi", "vim", "view", "nano", "emacs", "awk", "gawk", "sed", "cut", "sort", "uniq", "tee", "diff",
             "yq", "jq", "grep", "egrep", "rg", "Get-Content"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "bash", "sh", "zsh"}
PREFIX_WORDS = {"sudo", "env", "command", "exec", "time", "nice", "xargs"}
JQ_KEYS_RE = re.compile(r"""^\s*jq\s+(-[a-zA-Z]+\s+)*(?P<q>['"]?)\s*(\.[A-Za-z0-9_.\[\]"]*\s*\|\s*)?"""
                        r"""(keys|keys_unsorted|length|type|paths|leaf_paths|has\("[^"]*"\)|has\('[^']*'\))"""
                        r"""(\s*\|\s*(length|sort))?\s*(?P=q)(\s|$)""")
GREP_QUIET_RE = re.compile(r"^\s*(grep|egrep|rg)\s+(\S+\s+)*?(-[A-Za-z]*[cqlL][A-Za-z]*|--count|--quiet|--files-with-matches|--files-without-match)(\s|$)")
OPEN_CALL_RE = re.compile(r"(open|read_text|read_bytes|load|loads|readFileSync|readFile|File\.read|slurp|expanduser)\s*\(")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")


def secret_regexes():
    homes = [re.escape(HOME), r"\$HOME", r"\$\{HOME\}", "~"]
    out = []
    for pat in SECRET_PATTERNS:
        rest = pat[1:]  # "~" を外した残り
        out.append(re.compile("(" + "|".join(homes) + ")" + rest))
    return out


SECRET_RES = secret_regexes()


def secret_in(text: str) -> str | None:
    for rx in SECRET_RES:
        m = rx.search(text)
        if m:
            return m.group(0)
    m = DOTENV_RE.search(text)
    if m:
        return m.group(0).strip(" /'\"=")
    return None


def secret_path(path: str) -> str | None:
    if not path:
        return None
    p = os.path.expanduser(path)
    hit = secret_in(p)
    if hit:
        return hit
    base = os.path.basename(p)
    if DOTENV_RE.search(" " + base + " "):
        return base
    return None


def first_word(seg: str) -> str:
    for w in seg.split():
        if ASSIGN_RE.match(w) or w in PREFIX_WORDS:
            continue
        return os.path.basename(w.strip("(`"))
    return ""


def split_heredoc(cmd: str) -> tuple[list[str], list[str]]:
    """（ヒアドキュメントの本体を除いた行, 本体の行）に分ける。"""
    head, body, delim = [], [], None
    for line in cmd.splitlines():
        if delim is not None:
            if line.strip() == delim:
                delim = None
            else:
                body.append(line)
            continue
        head.append(line)
        m = re.findall(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", line.replace("<<<", ""))
        if m:
            delim = m[-1]
    return head, body


def bash_dumps(cmd: str) -> str | None:
    if "CR_SKIP_SECRET_GUARD=1" in cmd or not secret_in(cmd):
        return None
    head, body = split_heredoc(cmd)
    words = []
    for seg in re.split(r"\|\||&&|[;|\n]", "\n".join(head)):
        w = first_word(seg)
        words.append(w)
        hit = secret_in(seg)
        if not hit or w not in DUMP_CMDS | INTERPRETERS:
            continue
        if w == "jq" and JQ_KEYS_RE.match(seg.strip()):
            continue
        if w in ("grep", "egrep", "rg") and GREP_QUIET_RE.match(seg.strip()):
            continue
        return hit
    # python3 - <<EOF の本体で資格情報のファイルを開く形。名前が文面に出るだけ（記録を書き足すスクリプト等）では
    # 止めないよう、開く・読む呼び出しと同じ行にある時だけ見る。.env は文章に出やすいので、ホームの分だけ
    if body and INTERPRETERS & set(words):
        for line in body:
            if not OPEN_CALL_RE.search(line):
                continue
            for rx in SECRET_RES:
                m = rx.search(line)
                if m:
                    return m.group(0)
    return None


def block(what: str, how: str) -> None:
    print(f"""資格情報の関門: {what}（{how}）
資格情報を持つファイルの中身は、ツールの出力としてモデルへの入力と会話の記録に残り、消せません。

**キーの有無・件数だけを見る読み方にしてください。**
  - JSON: jq 'keys' <ファイル> ／ jq 'has("キー")' <ファイル> ／ jq '.mcpServers | keys' <ファイル>
  - 行の形式（.env・credentials）: grep -c '^キー=' <ファイル> ／ grep -q '^キー=' <ファイル> && echo ある
値そのものが要るなら、利用者に頼んでください（値を会話に書かず、設定だけ直してもらう）。

このツールの呼び出しは実行されていません。利用者が中身を見てよいと決めた時だけ、
Bashのコマンドの先頭に CR_SKIP_SECRET_GUARD=1 を付けて通せます。""", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    if tool == "Read":
        hit = secret_path(ti.get("file_path", ""))
        if hit:
            block(f"資格情報のファイル {hit} をReadで読もうとしています", "Readは中身を丸ごと返す")
    elif tool == "Grep":
        hit = secret_path(ti.get("path", ""))
        if hit and ti.get("output_mode") == "content":
            block(f"資格情報のファイル {hit} から合う行を出そうとしています", "Grepのoutput_mode=content")
    elif tool == "Bash":
        hit = bash_dumps(ti.get("command", ""))
        if hit:
            block(f"資格情報のファイル {hit} の中身を出すコマンドです", "cat・jq・grep・python等で中身が出る")


if __name__ == "__main__":
    main()
