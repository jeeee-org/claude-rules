# 要件 / スコープ

> 決めたこと（要求・方針・作業・予定）とスコープ、未決事項。**進み具合は PROGRESS.md**（計画の本体を二重に持たない）。決まった／変わったら即更新し、**片付いたら消す**（経緯は checkpoints/ に残る）。

最終更新: 2026-09-19

## 目的・スコープ
- Claude Code / Codex のグローバル共通ルール（`rules/*.md`）と`init-rules`スキルを、複数PCへ`install.sh`＋マーカーブロック方式で配布・同期する。
- 対象は「全PJに恒久的に効く決まり」だけ。PJ固有の差分は各PJの`CLAUDE.md`に置く（グローバル §7）。
- 出力スタイル（`~/.claude/output-styles/`）は配布対象外。文章の決まりは`rules/*.md`の§8・§9へ一本化する。

## 進行中の作業

> 依頼されたらここへカードを立ててから動く。**終わったら消して`PROGRESS.md`の完了へ1行**。

### 見出しの改名（2026-09-19起票）
- **何をする** = `init-rules`の`REQUIREMENTS.md`雛形の`## 要求・方針`を`## 決定・方針`へ改名する（今回足した`## 要求`と紛らわしいため）
- **叶っている状態** = 雛形と、節名を指している`migrate-rules`の記述が新しい名前で揃っている
- **現在地**（2026-09-19）= 着手
- **作業ログ** = `checkpoints/*-見出しの改名-*`（0件）

## やること / バックログ
- 既存PJを、開いた時に`/migrate-rules`で記録ルールの改訂に揃える（checkpointの移動・`REQUIREMENTS.md`の新設・ADR節の振り分け・`NOTES.md`の整理）。checkpointを移すかはPJごとにユーザーが決める（2026-09-14時点で未移行は17PJ。kakeiboとdiscは移行済み）。
- 他PCでclaude-rulesの**cloneを取り直して**`./install.sh`（2026-09-17にリポを作り直したため。消す前に`IMPROVEMENTS.md`への未pushの追記を確認する）。quorumは`git pull && ./install.sh`で、installがトリアージブロックの残骸を取り除く。`settings.json`の分類フック登録は各PCで手で外す。
- `rules/codex-global-rules.md`の圧縮（残量3,059Bで急がない。Claude側と同じ観点で他所と重複する語を畳む）。

## 未決事項
- [ ] 常時トリアージ規則を廃止した今、`hooks/triage-classifier.sh`・`hooks/triage-rubric.txt`・`skills/codex-triage/`（opt-inの分類ツール）を配布し続けるか。
- [ ] `migrate-rules`のCodex版を作るか（2026-09-14にClaude版だけ作った。Codexをメインに使うPJで同じ移行の需要があるか未確認）。
