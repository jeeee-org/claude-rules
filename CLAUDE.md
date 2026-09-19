# CLAUDE.md — claude-rules

Claude Codeへのプロジェクト指示書。**会話開始時に必ず読む。**
共通の進行管理・Git・記録ルールはグローバル`~/.claude/CLAUDE.md`に従う。ここには**このPJ固有のことだけ**を書く。

## このプロジェクト固有の前提

- Claude Code / Codexの**グローバル共通ルールとinit-rulesスキルを複数PCへ配布・同期する**リポ。`install.sh` +マーカーブロック方式（quorumと同じ）。
- **最大のリスク＝正本の取り違え**。`~/.claude/CLAUDE.md`と`~/.codex/AGENTS.md`の**マーカーブロック内を直接編集しない**（次回installで消える）。編集するのは常にこのリポ側：
  - Claude共通ルール → `rules/global-rules.md`
  - Codex共通ルール → `rules/codex-global-rules.md`（Claude側と自動同期しない。**片方を変えたらもう片方も見る**）
  - スキル → `skills/<name>/SKILL.md`
- ルールを変えたら必ず`./install.sh`でローカル反映してからコミットする（README「ルールを変更するとき」の手順）。
- **自分自身に効くルールを書き換えるリポ**である点に注意。変更は次セッション以降の全PJの挙動を変える。

## サイズ上限（グローバル§2の実務メモ）

`~/.claude/CLAUDE.md`の上限は**14,336B**（1024系）。2026-09-15にquorumのトリアージブロックを廃止したので、いまはclaude-rulesブロックだけが載る。`rules/global-rules.md`に追記したら`./install.sh`末尾の`tools/check-limits.sh`の判定を必ず確認する。

## 4軸ドキュメント

2026-09-12に`/init-rules`で整備済み。`README.md`は構成・手順の正本のまま。**README「経緯」は2026-09-12までの履歴として据え置き、以後の経緯は`checkpoints/`に書く**（READMEの経緯欄には追記しない）。

## REQUIREMENTS.mdの性質

- ルールと配布の仕組みそのものへの**改善案の受け皿**（他PCからの逆輸入・運用で出たズレ）。機能仕様は持たない。
- **要求の面の形**（グローバル§4）= **「追加要求: <題>」節を横に並べる**（窓口型）。改善案が随時・独立に来て終わりが無いため、上から順に叶える表は合わない。**節はカードに収まらない中身が出た時に作る**（無いうちは空節を置かない）。

## Git運用（グローバル§5の差分）

- リモート: `https://github.com/jeeee-org/claude-rules.git`（**public**・個人OSS）
- **main直接編集・直pushでよい**（§5.1 worktree必須の例外）。
- push: グローバル§5の既定どおり**1作業ごとにcommit＋自動push**（事前承認不要）。
- コミット規約: 日本語subject 1行（50字目安）＋ 空行 ＋ bodyに「何を・なぜ・どう・影響範囲」。
- AI署名（`Co-Authored-By: Claude` / `🤖 Generated with ...`）は**付けない**（既存コミットに合わせる）。
- ツール名quorum / claude-rulesはこのリポの主題なのでコミット本文に書いてよい（§5.2禁止①の例外）。

## その他

- ユーザーとは日本語でやり取りする。ドキュメントも日本語で書く。
