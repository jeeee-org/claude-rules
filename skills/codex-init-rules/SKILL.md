---
name: init-rules
description: 現在のプロジェクトにCodex用の4軸 + checkpoint構成を立ち上げる。AGENTS.md / REQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/の不足分だけを生成する。
---

# init-rules — Codex版

claude-rulesの共通ルールをPJの`AGENTS.md`の先頭へ書き込み、対象PJを初期化する（共通ルールはグローバルに置かない。2026-09-26〜）。既存ファイルは絶対に上書きせず、不足分だけ作る。

1. `git rev-parse --show-toplevel`と既存ファイルを確認する。
2. PJが開発中心か調査中心か、Gitブランチ・push・コミット方針を確認する。明らかな項目は推測可、不明事項は「未定」とする。
3. `install-rules`スキルの「1つのPJ」の手順で、読み手（既定は両方）と個人の運用を選んでもらい、共通ルールを`AGENTS.md`の先頭へ書き込む（cloneの場所は`dirname "$(readlink -e ~/.codex/skills/init-rules/IMPROVEMENTS.md)"`）。続けて、不足している次のファイルだけを作る。
   - `AGENTS.md`: PJの目的、最大リスク、REQUIREMENTSの性質（§4の要求の面の形——「追加要求: <題>」節を横に並べる窓口型か、「要件」の表を上から順に叶える終わりのある案件か——をここで1つ宣言する）、Git差分、技術・検証・文書規約。共通ルールのブロックの下に書き、共通ルールの中身は複製しない。
   - `REQUIREMENTS.md`: 目的・スコープ、進行中の作業カード（1作業1枚。何をする／叶っている状態／現在地／待ち／作業ログ）、やること/バックログ、要求（カードに収まらない中身。`AGENTS.md`で宣言した片方の形だけを使い、両方は置かない。「叶っている状態」はカードにあるので複写しない。1節50行が目安）、決定・方針（決めた仕様・方針・決定。日付付き1行。理由は`NOTES.md`）、未決事項。生きている分だけを残し、片付いたら消す（経緯はcheckpointに残る）。
   - `PROGRESS.md`: いまの状態だけ（現フェーズ、次の一手Top 3、完了、進行中）。計画の本体は`REQUIREMENTS.md`に置き、二重に持たない。60行以内を目安にする。
   - `NOTES.md`: 判断理由、学び、罠。項目の頭に取得日を書き、いま効く学びだけを残す。
   - `checkpoints/<今日>-初期構成.md`: 初期化内容の詳細ログ。以後も`checkpoints/YYYY-MM-DD-作業名-中身.md`（リポ直下、どちらも日本語の短い語。作業名はカードの見出しと同じ語）で1日1作業1ファイル。
4. 生成物を確認し、共通ルール§5に従って1コミットにする。pushは共通ルールで「自動push」を選んだ場合だけ行う。

Gitリポジトリ自体が無い場合、`git init -b main`は実行できる。ただしGitHubリポジトリ作成や公開など外向き操作は、名前・所有者・可視性をユーザーに確認してから行う。

PJのルールファイルは`AGENTS.md`に統一する（Claude Codeも直接読む）。既存`CLAUDE.md`があるPJは、このスキルでなく`install-rules`で`AGENTS.md`へ統一する（移す判断が要るため）。

## 改善案の記録

共通ルールや配布の仕組みについて気づいたことは`~/.codex/skills/init-rules/IMPROVEMENTS.md`（claude-rulesリポrootへのsymlink）へ末尾追記する。書く前に`readlink -e`でリンクの健全性を確認し、切れていたら追記せずclaude-rulesの`install.sh`を再実行する。ルール本体（`rules/common-rules.md`）は編集しない。反映はclaude-rulesのcloneを持つPCで行う。このファイルは公開リポに入るので、業務PJの内部ファイル名・ツール名・規約の具体値（関門の本数・上限のバイト値・社内PCの制約）と、個人の機材名やIPは書かず、動作で書く（「内部スクリプトで検査」ではなく「公開手順の機械検査で捕まえる」）。
