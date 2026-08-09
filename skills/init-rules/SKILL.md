---
name: init-rules
description: 現在のプロジェクトに共通の進行管理構成（4軸 + checkpoint + Git/メモ規約）を立ち上げる。グローバル ~/.claude/CLAUDE.md のルールに沿って、CLAUDE.md / REQUIREMENTS.md / PROGRESS.md / NOTES.md / docs/checkpoints/ の雛形を生成する。新規PJの初期化や、既存PJをこの方式に揃えたい時に使う。
---

# init-rules — プロジェクト構成の立ち上げ

グローバル `~/.claude/CLAUDE.md` で定義した共通骨格（4軸 + checkpoint, 進行ルール, Git, memory 不使用）に沿って、対象プロジェクトに必須ファイルの雛形を作る。**既存ファイルは絶対に上書きしない**（無いものだけ作る）。

## 手順

### 1. 現状確認
- `git rev-parse --show-toplevel` でリポジトリルートを確認。
- 既存の `CLAUDE.md` / `REQUIREMENTS.md` / `PROGRESS.md` / `NOTES.md` / `docs/checkpoints/` の有無を確認。**既にあるものは触らない**。何が在って何を作るかをユーザーに伝える。

### 2. PJの性質を確認（雛形の文言が変わる）
ユーザーに簡潔に確認する（不明なら聞く、明らかなら推測して進めてよい）：
- **PJの種類**：①コード/プロダクト開発 か ②調査・ドキュメント中心 か（REQUIREMENTS の役割が「機能仕様」か「調査スコープ」かに効く）。
- **Git**：`main` 直 push か feature ブランチか／**push を止めるか**（グローバル §5 の既定は「リモートがあれば 1作業ごとに自動 push」。止めたい時だけ「push はユーザー指示時のみ」を明示）。
- **コミット規約**：Conventional Commits か 日本語要約1行 か。

### 2.5 Git ブートストラップ（リポジトリが無い時だけ）
`git rev-parse` がリポジトリ外を示した場合のみ実施。既にリポジトリなら丸ごとスキップする。**リモート作成は外向き操作なので、実行前にリポジトリ名と private で良いかをユーザーに確認してから行う。**
1. `git init`（既定ブランチを `main` に：`git init -b main`）。
2. コミットメール（GH007 回避）：`git config user.email jeeee4@users.noreply.github.com`。
3. リポジトリ名を決める（既定はディレクトリ名）。**初回は private** で GitHub の `jeeee-org` org に作成し origin を設定：
   ```bash
   gh repo create jeeee-org/<name> --private --source=. --remote=origin
   ```
   - `gh` が未認証なら `gh auth status` で確認し、ユーザーに `gh auth login` を促す（私の側ではログインできない）。
   - 公開したくなった時は別途 `gh repo edit jeeee-org/<name> --visibility public`（公開は不可逆的影響があるので必ず確認の上で）。
4. この時点では push しない（初回 push は §4 で、雛形コミット後に方針に従って行う）。

### 3. 雛形を生成（無いものだけ）

**`CLAUDE.md`（プロジェクト用スタブ）** — グローバルを継承し、固有差分だけ書く：
```markdown
# CLAUDE.md — <プロジェクト名>

このファイルは Claude Code へのプロジェクト指示書。**会話開始時に必ず読む。**
共通の進行管理・Git・記録ルールは グローバル `~/.claude/CLAUDE.md` に従う。
ここには**このPJ固有のことだけ**を書く。

## このプロジェクト固有の前提
- <何のPJか・目的>
- **最大のリスク**：<スコープ膨張 / 鮮度落ち など>
- <その他の前提>

## REQUIREMENTS.md の性質
- <「機能仕様・ルールサブセット」 or 「調査スコープ・対象バックログ」>
- <`notes/` 等の独自慣習があればここに>

## Git 運用（グローバル §5 の差分）
- リモート: `<url>`（**private/public**）
- デフォルトブランチ: `main`（<feature ブランチを作る/作らない>）
- コミット規約: <Conventional Commits / 日本語要約1行>
- push 方針: <「グローバル §5 の既定どおり 1作業ごとに commit + 自動 push」 or 「push はユーザー指示時のみ（オプトアウト）」>

## その他固有ルール
- 技術スタック / スキル化方針 / ドキュメント規約 など（あれば）
- ユーザーは日本語でやり取りする。ドキュメントも日本語で書く。
```

**`REQUIREMENTS.md`**：
```markdown
# 要件 / スコープ

> 何を作るか/調べるか・仕様/スコープ・未決事項。スコープが変わったら即更新する。

最終更新: <YYYY-MM-DD>

## 目的・スコープ
（ここに）

## 対象 / バックログ
（ここに）

## 未決事項
- [ ] （ここに）
```

**`PROGRESS.md`**：
```markdown
# 進捗

> 何が終わって、何が進行中で、次に何をやるか。**このファイルは常にスリムに保つ。**
> 範囲は REQUIREMENTS.md、学び/罠は NOTES.md、詳細ログは docs/checkpoints/。

最終更新: <YYYY-MM-DD>

## 現在のフェーズ
（ここに）

## 次にやること (Top 3)
1.
2.
3.

## 完了
- [x] <YYYY-MM-DD> 初期構成を /init-rules で立ち上げ → [checkpoint](docs/checkpoints/<YYYY-MM-DD>.md)

## 進行中
(なし)

## ADR（意思決定の記録）
-
```

**`NOTES.md`**：
```markdown
# 学び・方法論（NOTES）

> 要件でも進捗でもない、**進め方・設計判断の理由・ハマりどころ・罠**を残す（メタな学び）。
> 肥大化したら checkpoint 方式（docs/checkpoints/）に逃がす。

最終更新: <YYYY-MM-DD>

## （セクションは必要になったら足す）
```

**`docs/checkpoints/<YYYY-MM-DD>.md`**（初日分）：
```markdown
# <YYYY-MM-DD> checkpoint

## 初期構成の立ち上げ（/init-rules）
- グローバル `~/.claude/CLAUDE.md` の共通骨格に沿って 4軸 + checkpoint を作成。
- PJ種別: <①開発 / ②調査>。Git: <方針>。
```

> 日付は実際の今日の日付を使う（環境のシステムリマインダ `currentDate` を参照）。`docs/checkpoints/` ディレクトリを作る。

### 4. 確認とコミット
- 生成したファイル一覧をユーザーに見せる。
- Git ルール（グローバル §5）に従ってコミット（雛形＋ `.gitignore` 等があれば一緒に）。**リモートがあれば push まで自動**。PJ側に「push はユーザー指示時のみ」の明示がある時だけ止める。
- §2.5 で新規作成したリポは、初回 push（`git push -u origin main`）で origin/main を確立する。これも push 方針に従う（既定は自動、オプトアウト宣言があれば確認）。

## 注意
- **上書き厳禁**。既存ファイルがあれば差分提案にとどめ、勝手に置き換えない。
- 各雛形の `<...>` プレースホルダは確認した内容で埋める。不明なものは「（未定）」で残し、捏造しない。
