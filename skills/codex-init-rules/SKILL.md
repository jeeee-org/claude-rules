---
name: init-rules
description: 現在のプロジェクトに Codex 用の4軸 + checkpoint構成を立ち上げる。AGENTS.md / REQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/ の不足分だけを生成する。
---

# init-rules — Codex版

グローバル `~/.codex/AGENTS.md` に沿って対象PJを初期化する。既存ファイルは絶対に上書きせず、不足分だけ作る。

1. `git rev-parse --show-toplevel` と既存ファイルを確認する。
2. PJが開発中心か調査中心か、Gitブランチ・push・コミット方針を確認する。明らかな項目は推測可、不明事項は「未定」とする。
3. 不足している次のファイルだけを作る。
   - `AGENTS.md`: PJの目的、最大リスク、REQUIREMENTSの性質、Git差分、技術・検証・文書規約。グローバル規則は複製しない。
   - `REQUIREMENTS.md`: 目的・スコープ、決めた要求・方針・決定（日付付き1行。理由は`NOTES.md`）、やること/バックログ（予定を含む）、未決事項。生きている分だけを残し、片付いたら消す（経緯はcheckpointに残る）。
   - `PROGRESS.md`: いまの状態だけ（現フェーズ、次の一手Top 3、完了、進行中）。計画の本体は`REQUIREMENTS.md`に置き、二重に持たない。60行以内を目安にする。
   - `NOTES.md`: 判断理由、学び、罠。項目の頭に取得日を書き、いま効く学びだけを残す。
   - `checkpoints/<今日>-初期構成.md`: 初期化内容の詳細ログ。以後も `checkpoints/YYYY-MM-DD-作業内容.md`（リポ直下、作業内容は日本語）で作業のまとまりごとに1ファイル。
4. 生成物を確認し、グローバルGit規則に従って1コミットにする。pushはPJが明示的に自動pushを許可した場合だけ行う。

Gitリポジトリ自体が無い場合、`git init -b main` は実行できる。ただしGitHubリポジトリ作成や公開など外向き操作は、名前・所有者・可視性をユーザーに確認してから行う。

Claude Codeと併用するPJで既存 `CLAUDE.md` がある場合も変更しない。共通の4文書とcheckpointは両LLMで共有し、LLM固有指示だけ `AGENTS.md` / `CLAUDE.md` に分離する。

## 改善案の記録

共通ルールや配布の仕組みについて気づいたことは `~/.codex/skills/init-rules/IMPROVEMENTS.md`（claude-rules リポ root への symlink）へ末尾追記する。書く前に `readlink -e` でリンクの健全性を確認し、切れていたら追記せず claude-rules の `install.sh` を再実行する。ルール本体（`rules/*.md`）は編集しない。反映は claude-rules の clone を持つPCで行う。このファイルは公開リポに入るので、業務PJの内部ファイル名・ツール名・規約の具体値（関門の本数・上限のバイト値・社内PCの制約）と、個人の機材名やIPは書かず、動作で書く（「内部スクリプトで検査」ではなく「公開手順の機械検査で捕まえる」）。
