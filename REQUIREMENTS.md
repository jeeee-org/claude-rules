# 要件 / スコープ

> 決めたこと（要求・方針・作業・予定）とスコープ、未決事項。**進み具合はPROGRESS.md**（計画の本体を二重に持たない）。決まった／変わったら即更新し、**片付いたら消す**（経緯はcheckpoints/に残る）。

最終更新: 2026-09-20

## 目的・スコープ
- Claude Code / Codexのグローバル共通ルール（`rules/*.md`）と`init-rules`スキルを、複数PCへ`install.sh`＋マーカーブロック方式で配布・同期する。
- 対象は「全PJに恒久的に効く決まり」だけ。PJ固有の差分は各PJの`CLAUDE.md`に置く（グローバル§7）。
- 出力スタイル（`~/.claude/output-styles/`）は配布対象外。文章の決まりは`rules/*.md`の§8・§9へ一本化する。

## 進行中の作業

> 依頼されたらここへカードを立ててから動く。**終わったら消して`PROGRESS.md`の完了へ1行**。

(なし)

## 要求

> カードに収まらない中身。**「追加要求: <題>」を横に並べる**（窓口型）。着手は別途カードを立ててから。

### 追加要求: `.claude`と`.codex`の統一（2026-09-20新設）

- **何に困っているか** = 同じ内容の共通ルールを`rules/global-rules.md`と`rules/codex-global-rules.md`の2枚、`init-rules`を`skills/init-rules`と`skills/codex-init-rules`の2枚で保守している。「片方を変えたらもう片方も見る」が常時コスト。
- **層ごとに状況が違う**（ここを混ぜると判断を誤る）:
  - **PJ層のルール = 解決済み**。2026-09-18のv2.1.277でClaude CodeがAGENTS.mdを直接読むようになった。
  - **グローバル層のルール = 未解決**。`~/.codex/AGENTS.md`はClaudeの探索経路（作業dirとその祖先）の外で、今後も読まれる見込みは無い。agents.md本体のissue #91が共通の置き場`~/.config/agents/AGENTS.md`を提案中だが**提案段階**。
  - **skills = フォーマットは決着済み**。Agent Skills Open Standard（2025-12公開、Linux Foundation AAIF管理、32以上のツールが実装）。残るのは置き場（`~/.claude/skills/`と`~/.codex/skills/`）だけで、**ルールより一段先に進んでいる**。
- **選択肢**（2026-09-20時点。どれも未着手）:
  - A. 標準（`~/.config/agents/AGENTS.md`）を待つ。仕様確定→Codex移行→Claude準拠の3段が要り、順調でも1〜2年。
  - B. グローバルCLAUDE.mdをやめ、内容をPJ層へ降ろす。ベンダ協力が不要で**今日できる唯一の道**。PJ側は`CLAUDE.md`をやめて`AGENTS.md`1本にする必要がある。
  - C. skillsだけ先に突き合わせる。対象は実質`init-rules`1組（`migrate-rules`はClaude専用、`codex-triage`はCodex専用で突き合わせ相手が無い）。
- **どの道でも消えない作業** = 中身の突き合わせ。`rules/*`が218行、`init-rules`が203行ずれている。1枚になればClaude専用の記述（§3のサブエージェント関門、スキルのパス）をCodexも読むので、**条件付きブロックの記法を決める判断**は避けられない。ベンダが何を出しても減らない。
- **効く含意** = Bを採る時もCを採る時も条件付きブロックの判断が発生する。Cのほうが対象が小さいので、**その判断を安く下せる場所**。
- **実測した挙動**は`NOTES.md`「配布の仕組み」へ。

## やること / バックログ
- 既存PJを、開いた時に`/migrate-rules`で記録ルールの改訂に揃える（checkpointの移動・`REQUIREMENTS.md`の新設・ADR節の振り分け・`NOTES.md`の整理）。checkpointを移すかはPJごとにユーザーが決める（2026-09-14時点で未移行は17PJ。kakeiboとdiscは移行済み）。
- 他PCでclaude-rulesの**cloneを取り直して**`./install.sh`（2026-09-17にリポを作り直したため。消す前に`IMPROVEMENTS.md`への未pushの追記を確認する）。quorumは`git pull && ./install.sh`で、installがトリアージブロックの残骸を取り除く。`settings.json`の分類フック登録は各PCで手で外す。
- `rules/codex-global-rules.md`の圧縮（残量3,059Bで急がない。Claude側と同じ観点で他所と重複する語を畳む）。

## 未決事項
- [ ] 常時トリアージ規則を廃止した今、`hooks/triage-classifier.sh`・`hooks/triage-rubric.txt`・`skills/codex-triage/`（opt-inの分類ツール）を配布し続けるか。
- [ ] `migrate-rules`のCodex版を作るか（2026-09-14にClaude版だけ作った。Codexをメインに使うPJで同じ移行の需要があるか未確認）。**統一の要求と連動**——1枚にするなら作る作らないの問いが消える。
- [ ] 統一のどの道を採るか（要求のA / B / C、または当面やらない）。
- [ ] 条件付きブロックの記法（`<!-- only:claude -->`など）。A・B・Cのどれでも要る。
- [ ] 2枚の文言をどちらの文体へ寄せるか。骨格は同じで書き方だけが違う（`rules/*`は太字の箇条書き対散文、表の列名も「いつ読む／いつ書く」対「読む時／書く時」）。
- [ ] Codexの`AGENTS.md`での`@path`参照がホーム直下（`@~/.claude/...`）まで届くか。届けばBのコピー量が「全文×N」から「1行×N」になる。2026-09-20は実測できず（Codexが`gpt-5.6-sol`で弾かれた）。
