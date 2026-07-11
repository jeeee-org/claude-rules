---
name: init-rules
description: 現在のプロジェクトに Codex 用の4軸 + checkpoint構成を立ち上げる。AGENTS.md / REQUIREMENTS.md / PROGRESS.md / NOTES.md / docs/checkpoints/ の不足分だけを生成する。
---

# init-rules — Codex版

グローバル `~/.codex/AGENTS.md` に沿って対象PJを初期化する。既存ファイルは絶対に上書きせず、不足分だけ作る。

1. `git rev-parse --show-toplevel` と既存ファイルを確認する。
2. PJが開発中心か調査中心か、Gitブランチ・push・コミット方針を確認する。明らかな項目は推測可、不明事項は「未定」とする。
3. 不足している次のファイルだけを作る。
   - `AGENTS.md`: PJの目的、最大リスク、REQUIREMENTSの性質、Git差分、技術・検証・文書規約。グローバル規則は複製しない。
   - `REQUIREMENTS.md`: 目的・スコープ、対象/バックログ、未決事項。
   - `PROGRESS.md`: 現フェーズ、次の作業Top 3、完了、進行中、ADR。60行以内を目安にする。
   - `NOTES.md`: 判断理由、学び、罠。
   - `docs/checkpoints/<今日>.md`: 初期化内容の詳細ログ。
4. 生成物を確認し、グローバルGit規則に従って1コミットにする。pushはPJが明示的に自動pushを許可した場合だけ行う。

Gitリポジトリ自体が無い場合、`git init -b main` は実行できる。ただしGitHubリポジトリ作成や公開など外向き操作は、名前・所有者・可視性をユーザーに確認してから行う。

Claude Codeと併用するPJで既存 `CLAUDE.md` がある場合も変更しない。共通の4文書とcheckpointは両LLMで共有し、LLM固有指示だけ `AGENTS.md` / `CLAUDE.md` に分離する。
