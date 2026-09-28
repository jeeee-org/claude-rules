#!/usr/bin/env bash
# claude-rules:commit-msg — gitのcommit-msgフック（PJの .git/hooks/commit-msg に置く）
# commitメッセージからAI帰属行（Co-Authored-By: Claude... / 🤖 Generated with... /
# noreply@anthropic.com）を取り除く。共通ルール§5.2 禁止②の最後の砦。
#
# なぜgitのフックなのか:
#   Claude CodeのPreToolUseの関門（push-attribution-guard.sh）は、commitとpushを同じ呼び出しで
#   行うとcommitがまだ無く、スクリプトの中のpushはコマンドに現れないので、どちらも素通りする
#   （IMPROVEMENTS 2026-09-28）。gitのフックは呼び出しの形によらずgit自身が呼ぶので漏れない。
#   Claude Code以外（Codex・人の手）のcommitにも効く。
#
# なぜ拒否でなく取り除くのか:
#   拒否するとPJの進捗コミット用スクリプトやループの工程が途中で落ちる。帰属行は消すべき1行で、
#   消せば済むので、commitは通して何を消したかをstderrへ出す。
#
# 置くのは claude-rules/tools/embed-rules.py（共通ルールを書き込む時）。前からあったcommit-msgは
# commit-msg.local へ退避し、ここから続けて呼ぶ。直すのはこのファイルでなく claude-rules 側の
# hooks/git-commit-msg.sh（次の書き込みで上書きされる）。
# 抜け道は CR_SKIP_ATTRIBUTION_GUARD=1（Claude Codeの関門と同じ指定）。
set -u

msg_file="${1:-}"
if [ -n "$msg_file" ] && [ -f "$msg_file" ] && [ "${CR_SKIP_ATTRIBUTION_GUARD:-}" != 1 ]; then
  ATTR_RE='^[[:space:]]*co-authored-by:.*(claude|anthropic)|noreply@anthropic\.com|generated with.*claude|^[[:space:]]*🤖'
  hits=$(grep -inE "$ATTR_RE" "$msg_file" 2>/dev/null)
  if [ -n "$hits" ]; then
    # 消した後の末尾の空行も落とす（トレーラの前の空行が残るため）
    grep -viE "$ATTR_RE" "$msg_file" |
      awk '{ lines[NR] = $0 } END { n = NR; while (n > 0 && lines[n] ~ /^[[:space:]]*$/) n--; for (i = 1; i <= n; i++) print lines[i] }' \
      > "$msg_file.cr-tmp" && mv "$msg_file.cr-tmp" "$msg_file"
    {
      echo "AI帰属行をcommitメッセージから取り除きました（共通ルール§5.2 禁止②。claude-rulesのcommit-msgフック）:"
      sed 's/^/  /' <<<"$hits"
    } >&2
  fi
fi

local_hook="$(dirname "$0")/commit-msg.local"
if [ -x "$local_hook" ]; then
  exec "$local_hook" "$@"
fi
exit 0
