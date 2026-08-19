# CLAUDE.md — claude-rules

Claude Code へのプロジェクト指示書。**会話開始時に必ず読む。**
共通の進行管理・Git・記録ルールは グローバル `~/.claude/CLAUDE.md` に従う。ここには**このPJ固有のことだけ**を書く。

## このプロジェクト固有の前提

- Claude Code / Codex の**グローバル共通ルールと init-rules スキルを複数PCへ配布・同期する**リポ。`install.sh` + マーカーブロック方式（quorum / cadence と同じ）。
- **最大のリスク＝正本の取り違え**。`~/.claude/CLAUDE.md` と `~/.codex/AGENTS.md` の**マーカーブロック内を直接編集しない**（次回 install で消える）。編集するのは常にこのリポ側：
  - Claude 共通ルール → `rules/global-rules.md`
  - Codex 共通ルール → `rules/codex-global-rules.md`（Claude 側と自動同期しない。**片方を変えたらもう片方も見る**）
  - スキル → `skills/<name>/SKILL.md`
- ルールを変えたら必ず `./install.sh` でローカル反映してからコミットする（README「ルールを変更するとき」の手順）。
- **自分自身に効くルールを書き換えるリポ**である点に注意。変更は次セッション以降の全PJの挙動を変える。

## サイズ上限（グローバル §2 の実務メモ）

`~/.claude/CLAUDE.md` は claude-rules / quorum / cadence の3ブロック合計で **14,336B**（1024系）。このリポが増やせるのは自分のブロック分だけなので、`rules/global-rules.md` に追記したら `./install.sh` 末尾の `tools/check-limits.sh` の判定を必ず確認する。

## 4軸ドキュメント

`REQUIREMENTS.md` / `PROGRESS.md` / `NOTES.md` / `docs/checkpoints/` は**未整備**。現状は `README.md` が構成・手順・経緯の正本。必要になったら `/init-rules` で立ち上げる（それまで checkpoint 生成は不要）。

## Git 運用（グローバル §5 の差分）

- リモート: `https://github.com/jeeee-org/claude-rules.git`（**public**・個人OSS）
- **main 直接編集・直 push でよい**（§5.1 worktree 必須の例外）。
- push: グローバル §5 の既定どおり **1作業ごとに commit + 自動 push**（事前承認不要）。
- コミット規約: 日本語 subject 1行（50字目安）＋ 空行 ＋ body に「何を・なぜ・どう・影響範囲」。
- AI 署名（`Co-Authored-By: Claude` / `🤖 Generated with ...`）は**付けない**（既存コミットに合わせる）。
- ツール名 quorum / cadence / claude-rules はこのリポの主題なのでコミット本文に書いてよい（§5.2 禁止①の例外）。

## その他

- ユーザーとは日本語でやり取りする。ドキュメントも日本語で書く。
