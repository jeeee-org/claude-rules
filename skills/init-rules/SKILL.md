---
name: init-rules
description: 現在のプロジェクトに共通の進行管理構成（4軸 + checkpoint + Git/メモ規約）を立ち上げる。グローバル ~/.claude/CLAUDE.md のルールに沿って、CLAUDE.md / REQUIREMENTS.md / PROGRESS.md / NOTES.md / checkpoints/ の雛形を生成する。新規PJの初期化や、既存PJをこの方式に揃えたい時に使う。
---

# init-rules — プロジェクト構成の立ち上げ

グローバル `~/.claude/CLAUDE.md` で定義した共通骨格（4軸 + checkpoint, 進行ルール, Git, memory 不使用）に沿って、対象プロジェクトに必須ファイルの雛形を作る。**既存ファイルは絶対に上書きしない**（無いものだけ作る）。

## 手順

### 1. 現状確認
- `git rev-parse --show-toplevel` でリポジトリルートを確認。
- 既存の `CLAUDE.md` / `REQUIREMENTS.md` / `PROGRESS.md` / `NOTES.md` / `checkpoints/` の有無を確認。**既にあるものは触らない**。何が在って何を作るかをユーザーに伝える。

### 2. PJの性質を確認（雛形の文言が変わる）
ユーザーに簡潔に確認する（不明なら聞く、明らかなら推測して進めてよい）：
- **PJの種類**：①コード/プロダクト開発 か ②調査・ドキュメント中心 か（REQUIREMENTS の役割が「機能仕様」か「調査スコープ」かに効く）。
- **Git**：`main` 直 push か feature ブランチか／**push を止めるか**（グローバル §5 の既定は「リモートがあれば 1作業ごとに自動 push」。止めたい時だけ「push はユーザー指示時のみ」を明示）。
- **コミット規約**：Conventional Commits か 日本語要約1行 か。

### 2.5 Git ブートストラップ（リポジトリが無い時だけ）
`git rev-parse` がリポジトリ外を示した場合のみ実施。既にリポジトリなら丸ごとスキップする。**リモート作成は外向き操作なので、実行前にリポジトリ名と private で良いかをユーザーに確認してから行う。**
1. `git init`（既定ブランチを `main` に：`git init -b main`）。
2. コミットメール（GH007 回避）：`git config user.email "$(gh api user --jq .login)@users.noreply.github.com"`（`gh` が使えなければユーザーに確認する）。
3. リポジトリ名を決める（既定はディレクトリ名）。**作成先の owner はユーザーに確認する**（個人アカウントか org か）。候補は `gh api user --jq .login`（個人）と `gh org list`（org）で出せる。**アカウント名・org 名をこのファイルに直書きしない**——このスキルは業務PCへも配布されるため。**初回は private** で作成し origin を設定：
   ```bash
   gh repo create <owner>/<name> --private --source=. --remote=origin
   ```
   - `gh` が未認証なら `gh auth status` で確認し、ユーザーに `gh auth login` を促す（私の側ではログインできない）。
   - 公開したくなった時は別途 `gh repo edit <owner>/<name> --visibility public`（公開は不可逆的影響があるので必ず確認の上で）。
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

> 決めたこと（要求・方針・作業・予定）とスコープ、未決事項。**進み具合は PROGRESS.md**（計画の本体を二重に持たない）。決まった／変わったら即更新し、**片付いたら消す**（経緯は checkpoints/ に残る）。

最終更新: <YYYY-MM-DD>

## 目的・スコープ
（ここに）

## 要求・方針
（決めた仕様・方針・決定。決めた時点で日付付き1行で書く。理由が非自明なら NOTES.md へ）

## やること / バックログ
（着手前の作業と予定。実行中・完了の状態は PROGRESS.md 側。片付いたら消す）

## 未決事項
- [ ] （ここに）
```

**`PROGRESS.md`**：
```markdown
# 進捗

> **いまの状態だけ**を置く——何が終わって、何が進行中で、次の一手は何か。**常にスリムに保つ。**
> 決めた要求・方針・予定は REQUIREMENTS.md、学び/罠は NOTES.md、詳細ログは checkpoints/。

最終更新: <YYYY-MM-DD>

## 現在のフェーズ
（ここに）

## 次の一手 (Top 3)
> REQUIREMENTS.md のバックログから直近の分だけを取り出す。
1.
2.
3.

## 完了
- [x] <YYYY-MM-DD> 初期構成を /init-rules で立ち上げ → [checkpoint](checkpoints/<YYYY-MM-DD>-初期構成.md)

## 進行中
(なし)

```

**`NOTES.md`**：
```markdown
# 学び・方法論（NOTES）

> 要件でも進捗でもない、**進め方・設計判断の理由・ハマりどころ・罠**を残す（メタな学び）。
> **いま効く学びだけ**を置く。項目の頭に取得日を書く（`- <YYYY-MM-DD> …`）。
> 似たトピックで開いた項目をその場で見直し、ルール・スキル・テストに昇格したら移した先を
> 1行残して消す／前提が変わって効かなくなったら消す／一回限りのログは checkpoints/ へ。

最終更新: <YYYY-MM-DD>

## （セクションは必要になったら足す）
```

**`checkpoints/<YYYY-MM-DD>-初期構成.md`**（初回分）：
```markdown
# <YYYY-MM-DD> 初期構成の立ち上げ（/init-rules）

- グローバル `~/.claude/CLAUDE.md` の共通骨格に沿って 4軸 + checkpoint を作成。
- PJ種別: <①開発 / ②調査>。Git: <方針>。
```

> 日付は実際の今日の日付を使う（環境のシステムリマインダ `currentDate` を参照）。リポ直下に `checkpoints/` ディレクトリを作る。ファイル名は `YYYY-MM-DD-作業内容.md` で、作業内容は日本語の短い語（作業のまとまりごとに1ファイル）。

### 4. 確認とコミット
- 生成したファイル一覧をユーザーに見せる。
- Git ルール（グローバル §5）に従ってコミット（雛形＋ `.gitignore` 等があれば一緒に）。**リモートがあれば push まで自動**。PJ側に「push はユーザー指示時のみ」の明示がある時だけ止める。
- §2.5 で新規作成したリポは、初回 push（`git push -u origin main`）で origin/main を確立する。これも push 方針に従う（既定は自動、オプトアウト宣言があれば確認）。

## 改善案の記録（運用ルール）

グローバル共通ルールや配布の仕組み（`install.sh` / `check-limits.sh`）について**使っていて気づいたこと**は、claude-rules の `IMPROVEMENTS.md` に書く。配置先は `~/.claude/skills/init-rules/IMPROVEMENTS.md` で、リポ root の正本への symlink（追記はそのまま git 管理下へ入り、再インストールでも消えない）。

- **書く前に `readlink -e ~/.claude/skills/init-rules/IMPROVEMENTS.md` で健全性を1回確認する。** 切れていたら追記せず、claude-rules の `install.sh` を再実行してから書く（リポを移動すると全PCのリンクが同時に切れ、追記が黙って落ちる）。
- 1件 = 日付＋状況＋気づき＋できれば改善案。**末尾へ追記**（古い順。先頭へ差し込むと他PCの clone と全項目 conflict する）。
- **`rules/global-rules.md` などの正本そのものは編集しない。** 反映は claude-rules の clone を持つPCで行う（README「ルールを変更するとき」）。
- PJ固有の学びはここではなく対象PJの `NOTES.md` へ。全PJに効く共通ルールの話だけを書く。
- **このファイルは公開リポに入る。** 業務PJの内部ファイル名・スクリプト名・ツール名・規約の具体値（関門の本数・上限のバイト値・社内PCの制約）と、個人の機材名やIPは書かない。**動作で書く**——「`<内部スクリプト名>`で検査」ではなく「公開手順の機械検査で捕まえる」。抽象化しても気づきの中身は残る。

## 注意
- **上書き厳禁**。既存ファイルがあれば差分提案にとどめ、勝手に置き換えない。
- 各雛形の `<...>` プレースホルダは確認した内容で埋める。不明なものは「（未定）」で残し、捏造しない。
