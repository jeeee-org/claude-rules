#!/usr/bin/env bash
# commit-record-guard.sh — PreToolUse（Bash）フック
# commitしようとした時に、作業の記録（REQUIREMENTS.md / PROGRESS.md / NOTES.md /
# checkpoints/）が一緒に変わっているかを見る。1つも無ければcommitを止めて差し戻す。
# 共通ルール§3「タスク完了時（必須）」の抜けを、自己申告から独立して捕まえるため。
#
# **判定できるのは「この呼び出しはcommitだけ」という形に限られる。** PreToolUseは
# コマンドの実行前に走るので、同じ呼び出しの中でファイルを書いてからcommitする形では、
# その書き込みがまだ起きていない（2台の実測で、記録なしのcommitが素通りした。
# IMPROVEMENTS 2026-09-18）。そこで**書き込みとcommitが同じ呼び出しにある時は、
# 判定せずに「分けて打つ」ことを求める**。git addだけなら、対象の変更は既にディスクにある。
#
# 設計方針:
#  - fail-open。判定できない時（jqもpython3も無い・gitの外・記録の5点を持たないリポ・
#    見るリポが決められない）は黙って通す。**別のリポを見て誤るより通す。**
#  - 禁止ではなく、意識した判断の強制。要らない時はコミットメッセージに`記録なし: <理由>`の行を
#    入れる（履歴に残り、pushの関門・後追いの監査もこの行で通る）。メッセージを読めない形なら
#    理由を述べて CR_SKIP_RECORD_GUARD=1 を付けて通す（コマンドに残るので、あとから見て分かる）。
#  - CLAUDE.md・AGENTS.md（PJのルール）は数えない。ルールだけを直したcommitも記録は要る。
#  - 止めた時は**コマンド全体が実行されない**。差し戻しの文面でそれを必ず言う
#    （準備まで済んだと誤解すると、次のcommitが空振りする）。
# 登録はclaude-rules/install.shが行う（~/.claude/settings.json のPreToolUse）。
# **本丸は hooks/push-record-guard.sh**（pushの直前なら、commitが既にあるので正確に判定でき、
# しかも止められる）。ここは早く気づくための入口で、見逃しの後追いは
# hooks/commit-record-audit.sh（PostToolUse）。三段でひと組。
# 効いているかは tools/check-record-guard.sh で、**作業するリポごとに**確かめる。
set -u

RECORD_RE='(^|/)(REQUIREMENTS|PROGRESS|NOTES)\.md$|(^|/)checkpoints/'
# コマンド中のパス（"..." / '...' / 素の語）
PATH_PAT='("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]+)'
GIT_COMMIT_RE='git[[:space:]]+((-C|-c)[[:space:]]+'"$PATH_PAT"'[[:space:]]+)*commit'
# ファイルを書く気配。これがcommitと同じ呼び出しにあると、PreToolUseでは中身が見えない
# cat/printf/echoは単体では書かない（書く時はリダイレクトが付くので、その形で捕まえる）。
# ヒアドキュメントの記号そのものは入れない——`git commit -F - <<'EOF'`はメッセージを渡すだけ
# **判定は引用符の中身を落としてから行う**（strip_quoted_args）。落とさないと、commit
# メッセージの中の`<...@...>`がリダイレクトに見える（IMPROVEMENTS 2026-09-20）
WRITE_RE='(^|[;&|(]|&&)[[:space:]]*(tee|touch|cp|mv|install|python3?|perl|ruby|node|bash|sh|zsh|awk|rsync|dd)[[:space:]]|[^0-9&>]>>?[[:space:]]*[^&[:space:]]|[[:space:]]sed[[:space:]]+-i'

input=$(cat) || exit 0
[ -n "$input" ] || exit 0

# JSONの取り出し。jqが無ければpython3で代える（どちらも無ければ通す）
read_json() { # read_json <キーのパス>
  if command -v jq >/dev/null 2>&1; then
    jq -r "$1 // empty" <<<"$input" 2>/dev/null
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
for k in sys.argv[1].lstrip(".").split("."):
    d = d.get(k) if isinstance(d, dict) else None
print(d if isinstance(d,str) else "")' "$1" <<<"$input" 2>/dev/null
  fi
}

unquote() { sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"; }
expand_home() { case "$1" in '~'|'~/'*) printf '%s' "$HOME${1#\~}" ;; *) printf '%s' "$1" ;; esac; }

# ヒアドキュメントの**本体だけ**を落とす。`<<`から後ろを全部切ると、その後ろにある
# commitが検出から漏れる（記録なしのcommitが素通りした原因。IMPROVEMENTS 2026-09-18）
strip_heredoc_bodies() {
  awk '
    function delim_of(line,   tmp, d, delim) {
      tmp = line
      gsub(/<<</, "\001", tmp)          # ヒアストリングは対象外
      delim = ""
      while (match(tmp, /<<-?[ \t]*("[^"]+"|\047[^\047]+\047|[A-Za-z_][A-Za-z0-9_]*)/)) {
        d = substr(tmp, RSTART, RLENGTH)
        sub(/^<<-?[ \t]*/, "", d)
        gsub(/["\047]/, "", d)
        delim = d                        # 同じ行に複数あれば最後のもの
        tmp = substr(tmp, RSTART + RLENGTH)
      }
      return delim
    }
    {
      if (skip != "") {                  # 本体の中：デリミタ行まで捨てる
        t = $0; sub(/^[ \t]+/, "", t)
        if (t == skip) skip = ""
        next
      }
      print
      skip = delim_of($0)
    }
  '
}

# 引用符（"…" / '…'）の**中身だけ**を落とす。記号は残すので語の切れ目は変わらない。
# リダイレクトの検出が、commitメッセージの中の記号を拾ってしまうのを防ぐ——
# `git commit -m "…<noreply@anthropic.com>" && git push` の `m>` と閉じ引用符が
# `[^0-9&>]>>?[[:space:]]*[^&[:space:]]` に当たっていた（IMPROVEMENTS 2026-09-20）。
# **誤検知そのものより、逃げ道が問題だった**——止められた側は-mをやめて-Fファイルへ回り、
# そのcommitは記録の関門の目を素通りした。関門は、外し方を教える形で外れてはいけない。
# 引用の状態は行をまたいで持ち越す（-mの本文は複数行になる）。
strip_quoted_args() {
  awk '
    {
      out = ""; n = length($0); i = 1
      while (i <= n) {
        c = substr($0, i, 1)
        if (q == "") {
          if (c == "\\") { out = out c; i += 2; continue }   # \X は展開されない1文字
          if (c == "\"" || c == "\047") { q = c; out = out c; i++; continue }
          out = out c; i++; continue
        }
        if (q == "\"" && c == "\\") { i += 2; continue }     # "…" の中の \" は閉じない
        if (c == q) { q = ""; out = out c; i++; continue }
        i++                                                 # 引用の中身は落とす
      }
      print out
    }
  '
}

[ "$(read_json '.tool_name')" = "Bash" ] || exit 0
# 呼ばれた印。配線が生きているかを、手で試さなくても観測値として読めるようにする
{ date +%s > "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.record-guard-seen"; } 2>/dev/null || true

cmd=$(read_json '.tool_input.command')
[ -n "$cmd" ] || exit 0

# 以後の判定は、ヒアドキュメントの本体を除いた部分に対して行う。印の判定も同じで、
# 文書やcommitメッセージの本文に印の名前を書いただけでは効かないようにする
head_part=$(strip_heredoc_bodies <<<"$cmd")

# 疎通確認（tools/check-record-guard.sh の②）。**呼ばれていれば必ず止める**ので、
# 「このリポでフックが起動しているか」だけを見られる。リポの状態も判定も通らない。
case "$head_part" in
  *CR_RECORD_GUARD_PROBE*)
    echo "記録の関門: 発火しています（疎通確認。このリポでは関門が効いています）" >&2
    exit 2 ;;
esac

# 本当にcommitを作ろうとしているか
grep -Eq "(^|[;&|(]|&&)[[:space:]]*${GIT_COMMIT_RE}([[:space:]]|\$)" <<<"$head_part" || exit 0

# 通す指定（理由を述べたうえでの明示。コマンドに残る）
case "$head_part" in *CR_SKIP_RECORD_GUARD*) exit 0 ;; esac
# 履歴を作らない・作り直すだけのものは対象外
case "$head_part" in *--dry-run*|*--amend*) exit 0 ;; esac

# 理由付きの例外: **このcommitのメッセージ**に`記録なし: <理由>`（`No-Record:`）の行があれば通す。
# 後追いの監査とpushの関門と同じ書き方で、理由が履歴に残る（環境変数との二重指定を要らなくする）。
# 見るのはcommitのメッセージだけ——`-m`の引数・`-F -`に渡すヒアドキュメント・`-F <ファイル>`。
# 同じ呼び出しで書く別のファイルの中身に同じ行があっても効かない。python3が無ければ見ない（環境変数で通す）
if command -v python3 >/dev/null 2>&1; then
  exempt=$(python3 - "$cmd" "$(read_json '.cwd')" <<'PY' 2>/dev/null
import os, re, sys
cmd, cwd = sys.argv[1], sys.argv[2] or os.getcwd()
EX = re.compile(r"^\s*(記録なし|No-Record)\s*[:：]", re.M)
lines = cmd.split("\n")
msgs = []
for i, line in enumerate(lines):
    m = re.search(r"\bgit\b[^\n;&|]*?\bcommit\b", line)
    if not m:
        continue
    seg = line[m.start():]
    rest = "\n".join([seg] + lines[i + 1:])
    hd = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", seg)
    if hd and re.search(r"(?:-F\s*-|--file[= ]-)(?:\s|$)", seg):
        body = []
        for x in lines[i + 1:]:
            if x.strip() == hd.group(2):
                break
            body.append(x)
        msgs.append("\n".join(body))
    for mm in re.finditer(r"(?:\s-m|\s--message)(?:=|\s+)(\"((?:[^\"\\]|\\.)*)\"|'([^']*)'|(\S+))", rest):
        msgs.append(mm.group(2) or mm.group(3) or mm.group(4) or "")
    ff = re.search(r"\s(?:-F|--file)(?:=|\s+)(\"([^\"]+)\"|'([^']+)'|(\S+))", seg)
    if ff and (ff.group(2) or ff.group(3) or ff.group(4)) != "-":
        try:
            msgs.append(open(os.path.join(cwd, os.path.expanduser(ff.group(2) or ff.group(3) or ff.group(4))), encoding="utf-8").read())
        except OSError:
            pass
print("1" if any(EX.search(x) for x in msgs) else "0")
PY
)
  [ "$exempt" = 1 ] && exit 0
fi

# 書き込みとcommitが同じ呼び出しにある形は、判定できない（書き込みはまだ起きていない）
if grep -Eq "$WRITE_RE" <<<"$(strip_quoted_args <<<"$head_part")"; then
  cat >&2 <<'MSG'
記録の関門: この呼び出しは、ファイルを書くのとcommitを一度に行っています。
PreToolUseはコマンドの実行前に走るので、書き込みがまだ起きておらず、記録が入るかを
判定できません（この形で記録なしのcommitが素通りしていました）。

**編集の呼び出しとcommitの呼び出しを分けてください。**
  1回目: ファイルを書く（記録もここで書く）
  2回目: git add と git commit だけ

このコマンドは**1行も実行されていません**。同じ呼び出しで準備していた分も、
やり直しになります。判定が要らないと分かっている場合だけ、理由を1行述べて
コマンドの先頭にCR_SKIP_RECORD_GUARD=1を付けて通してください。
MSG
  exit 2
fi

# 判定するリポを決める。実際のgitと同じ順で解く:
#   セッションのcwd → 先頭のcdの行き先 → git -C の指定（-Cが最優先）
cwd=$(read_json '.cwd')
[ -n "$cwd" ] || cwd=$PWD

case "$head_part" in
  cd\ *) target=$(sed -e 's/&&.*//' -e 's/;.*//' <<<"${head_part#cd }" | unquote)
         # evalしない（コマンド文字列をそのまま展開すると、ここが実行口になる）
         target=$(expand_home "$target")
         [ -n "$target" ] && [ -d "$target" ] && cwd=$target ;;
esac

# git -C <パス> commit ではそのリポで判定する。「git系はパスを毎回明示」を定めたPJが
# あり、worktreeのcommitを本体cloneの状態で判定すると、関門は両方向に誤る——
# worktreeに書いた記録が見えず止まる／本体に残った記録で素通りする（IMPROVEMENTS 2026-09-18）
git_call=$(grep -oE "$GIT_COMMIT_RE" <<<"$head_part" | tail -n1)
repo_opt=$(grep -oE -- "-C[[:space:]]+$PATH_PAT" <<<"$git_call" | tail -n1 | sed 's/^-C//' | unquote)
if [ -n "$repo_opt" ]; then
  repo_opt=$(expand_home "$repo_opt")
  case "$repo_opt" in /*) ;; *) repo_opt="$cwd/$repo_opt" ;; esac
  # 変数展開などでここでは解けない指定の時は、判定しない（別のリポを見て誤るより通す）
  [ -d "$repo_opt" ] || exit 0
  cwd=$repo_opt
fi

root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$root" ] || exit 0

# -zで読む。-z無しのporcelainは空白を含むパスを引用符で囲み、RECORD_REの(^|/)に掛からない
# （core.quotepathは非ASCIIだけの制御で、空白の引用は止まらない）。
# -zの改名はXY newの次に元の名前が別の要素で来るので、元の名前は読み捨てる
changed=""
while IFS= read -r -d '' entry; do
  changed+="${entry:3}"$'\n'
  case ${entry:0:1} in R|C) IFS= read -r -d '' _ ;; esac
done < <(git -C "$root" status --porcelain -z -uall 2>/dev/null)
[ -n "$changed" ] || exit 0   # 何も変わっていない＝commitするものが無い（gitが断る）

# このリポが記録の方式を使っているか（使っていないPJでは何も言わない）
git -c core.quotepath=false -C "$root" ls-files 2>/dev/null | grep -Eq "$RECORD_RE" ||
  grep -Eq "$RECORD_RE" <<<"$changed" || exit 0

grep -Eq "$RECORD_RE" <<<"$changed" && exit 0

cat >&2 <<MSG
記録の関門: このcommitに作業の記録が入っていません（見たリポ: $root）。
変更にREQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/のどれも含まれていません。

共通ルール§3「タスク完了時（必須）」= 作業ログをその作業のcheckpointへ、PROGRESS.mdの
完了と次の一手、要件・スコープの変化をREQUIREMENTS.mdへ、学びをNOTES.mdへ。

このコマンドは**1行も実行されていません**（git addも走っていません）。記録を書いて
から、準備の分ごと打ち直してください。この作業に記録が要らない場合は、コミット
メッセージに「記録なし: <理由>」の行を入れてください（履歴に残り、pushの関門もこれで通ります）。
メッセージを読めない形（エディタで書く等）なら、コマンドの先頭にCR_SKIP_RECORD_GUARD=1を付けて通します。
MSG
exit 2
