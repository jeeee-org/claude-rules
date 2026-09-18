# 要件 / スコープ

> 決めたこと（要求・方針・作業・予定）とスコープ、未決事項。**進み具合は PROGRESS.md**（計画の本体を二重に持たない）。決まった／変わったら即更新し、**片付いたら消す**（経緯は checkpoints/ に残る）。

最終更新: 2026-09-18

## 目的・スコープ
- Claude Code / Codex のグローバル共通ルール（`rules/*.md`）と`init-rules`スキルを、複数PCへ`install.sh`＋マーカーブロック方式で配布・同期する。
- 対象は「全PJに恒久的に効く決まり」だけ。PJ固有の差分は各PJの`CLAUDE.md`に置く（グローバル §7）。
- 出力スタイル（`~/.claude/output-styles/`）は配布対象外。文章の決まりは`rules/*.md`の§8・§9へ一本化する。

## 進行中の作業

> 依頼されたらここへカードを立ててから動く。**終わったら消して`PROGRESS.md`の完了へ1行**。

(なし)

## 要求・方針
- 正本は常にこのリポ側（`rules/global-rules.md` / `rules/codex-global-rules.md` / `skills/*/SKILL.md`）。生成物（`~/.claude/CLAUDE.md`等）のマーカー内は直接編集しない。
- 正本を編集するPCは1台（このclone）に限る。他PCの気づきは`IMPROVEMENTS.md`へ。
- Claude側とCodex側は自動同期しない。片方を変えたらもう片方も見る。
- 常時ロードの上限（グローバル14,336B / PJ CLAUDE.md 6,144B / PROGRESS.md 60行かつ12,288B）を守る。ルールを足す時は同時に畳む場所を探し、意味を落とさずバイトを削る。
- 見出し番号（§5.1・§5.2等）は据え置く。各PJの`CLAUDE.md`から参照されている。
- 常時ロードのルールにツール名を書かない（指す先の無い手順が残る）。動作で書く。
- 2026-09-12 README「経緯」は同日までの履歴として据え置き、以後の経緯は`checkpoints/`へ。READMEは構成・手順の正本のまま。
- 2026-09-12 決定（ADR）の独立した節は持たない。決定はここに日付付き1行、理由は`NOTES.md`。
- 2026-09-14 既存PJのcheckpoint移行は、判断の要らない部分（移動・見出し・リンクの張り直し・検査）だけをテスト付きのコマンドにする。作業内容の命名とADRの仕分けは人かClaudeが決める。
- 2026-09-15 常時トリアージの規則は持たない。quorumはユーザーが「quorumで」と明示した時だけ使う（自動分類フックも既定で登録しない）。
- 2026-09-17 このリポはpublic。改善メモにも記録にも、業務PJの内部の具体値（ファイル名・スクリプト名・ツール名・規約の値・社内の制約）と個人の環境の値を書かず、動作で書く。落とした値は対応表の形でも残さない。
- 2026-09-18 依頼された作業は`REQUIREMENTS.md`の「進行中の作業」節へ1作業1カード（何をする／叶っている状態／現在地／待ち／作業ログ）。checkpointは`YYYY-MM-DD-作業名-中身.md`とし、作業名はカードの見出しと同じ語にする。
- 2026-09-14 既存PJの記録ルールへの追従は、スキル`migrate-rules`（判断の手順）で行う。移動と突き合わせの機械作業はスキルから`tools/`のコマンドを呼び、その場のスクリプトで書き直さない。

## やること / バックログ
- 既存PJを、開いた時に`/migrate-rules`で記録ルールの改訂に揃える（checkpointの移動・`REQUIREMENTS.md`の新設・ADR節の振り分け・`NOTES.md`の整理）。checkpointを移すかはPJごとにユーザーが決める（2026-09-14時点で未移行は17PJ。kakeiboとdiscは移行済み）。
- 他PCでclaude-rulesの**cloneを取り直して**`./install.sh`（2026-09-17にリポを作り直したため。消す前に`IMPROVEMENTS.md`への未pushの追記を確認する）。quorumは`git pull && ./install.sh`で、installがトリアージブロックの残骸を取り除く。`settings.json`の分類フック登録は各PCで手で外す。
- `rules/codex-global-rules.md`の圧縮（残量3,795Bで急がない。Claude側と同じ観点で他所と重複する語を畳む）。

## 未決事項
- [ ] 常時トリアージ規則を廃止した今、`hooks/triage-classifier.sh`・`hooks/triage-rubric.txt`・`skills/codex-triage/`（opt-inの分類ツール）を配布し続けるか。
- [ ] 2026-09-18のカード導入を移行側へ波及させるか。`tools/migrate-checkpoints.py`とREADMEの説明が旧い名前の書式（`YYYY-MM-DD-作業内容.md`）のままで、`migrate-rules`にも既存PJへカードを新設する手順が無い。
- [ ] `migrate-rules`のCodex版を作るか（2026-09-14にClaude版だけ作った。Codexをメインに使うPJで同じ移行の需要があるか未確認）。
