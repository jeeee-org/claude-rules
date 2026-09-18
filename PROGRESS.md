# 進捗

> **いまの状態だけ**を置く——何が終わって、何が進行中で、次の一手は何か。**常にスリムに保つ。**
> 決めた要求・方針・予定は REQUIREMENTS.md、学び/罠は NOTES.md、詳細ログは checkpoints/。

最終更新: 2026-09-18

## 現在のフェーズ
運用中。2026-09-12に記録ルール（checkpointの粒度・要件と進捗の書き分け・片付け方・ADR節の廃止）を改めて全体を圧縮し、2026-09-15に常時トリアージ規則を廃止（quorumは明示呼び出しだけ）、`migrate-rules`をモノレポで壊れない形にした。2026-09-17に移行コマンドへ改名だけの入口とリンク切れの検査を足し、公開前の点検として業務・個人の具体値を抽象化したうえで履歴を1コミットへ畳みリポを作り直した。2026-09-18に進行中の作業カードを導入。グローバルCLAUDE.mdは11,548B（残り2,788B）。

## 次の一手 (Top 3)
> REQUIREMENTS.md のバックログから直近の分だけを取り出す。
1. 他PCでclaude-rulesの**cloneを取り直す**（2026-09-17に履歴を畳みリポを作り直したため。`git pull`は進まず、`reset --hard`では畳む前の版がそのPCに残る）。**消す前に`IMPROVEMENTS.md`への未pushの追記が無いか見る**（追記はclone内の正本に入る）。取り直したら`./install.sh`（symlinkの張り直しに必須）。quorumは`git pull && ./install.sh`。`settings.json`に分類フックが登録済みなら手で外す
2. 既存PJを開いたら`/migrate-rules`で記録ルールの改訂に揃える（未移行15PJ。モノレポのPJは残り16タスクを`--repo tasks/<name>`で1つずつ。置き場だけ揃ったタスクは改名だけの入口で回る）
3. （余裕があれば）Codex側ルールの圧縮

## 完了
- [x] 2026-09-18 カード導入と新しい命名を移行側（移行コマンド・`migrate-rules`・READMEの説明）へ波及。既存PJを揃えるとカードが立ち、checkpointが新しい書式になる → [checkpoint](checkpoints/2026-09-18-移行側の追従-命名とカードの波及.md)
- [x] 2026-09-18 依頼された作業を`REQUIREMENTS.md`の「進行中の作業」カードで持つ形にし、checkpointの名前を`YYYY-MM-DD-作業名-中身.md`へ（他PCからの改善案。Claude / Codex 両方のルールと両方の`init-rules`）→ [checkpoint](checkpoints/2026-09-18-作業カード-ルールとスキルへの導入.md)
- [x] 2026-09-17 公開前の点検（秘密情報はゼロ・社名等もゼロを確認）と、業務・個人の具体値の抽象化。仕上げに**履歴を1コミットへ畳み、リポを作り直して残骸も消した**（旧コミットは404を確認） → [checkpoint](checkpoints/2026-09-17-公開前の点検と抽象化.md)
- [x] 2026-09-17 移行コマンドに改名だけの入口（置き場は移済みで名前が古いPJ用）とリンク切れの検査を足した。外向きリンクの張り直しは既にあり、切れた2件は手の移動が素通りしたものと判明 → [checkpoint](checkpoints/2026-09-17-移行コマンドの改名モードとリンク検査.md)
- [x] 2026-09-15 改善メモ2件を反映：`migrate-checkpoints.py`をモノレポで壊れない形に（PJ単位の参照解決・`--repo`の統一）、`migrate-rules`の手順1・6・7でPJの`CLAUDE.md`の上書き宣言を守る → [checkpoint](checkpoints/2026-09-15-移行スクリプトのモノレポ対応.md)
- [x] 2026-09-15 常時トリアージ規則を廃止（quorumの注入・Codexの`$triage`必須・自動分類フック登録。quorum側は`f953b3d`）→ [checkpoint](checkpoints/2026-09-15-常時トリアージの廃止.md)
- [x] 2026-09-15 §2に「`PROGRESS.md`に更新履歴を積まない」を追加（他PCからの逆輸入、Claude / Codex両方）→ [checkpoint](checkpoints/2026-09-15-進捗の更新履歴の禁止.md)
- [x] 2026-09-15 `migrate-rules`をmeeting-scribeへ初めて通して出たズレ6件を、スキルと移行コマンドに反映 → [checkpoint](checkpoints/2026-09-15-移行スキルの初回適用で出たズレ.md)
- [x] 2026-09-14 既存PJを記録ルールの改訂に揃えるスキル`migrate-rules`と、移し漏れの突き合わせコマンドを追加（discの移行で踏んだ落ちた作業・heredocの罠を手順に固定）→ [checkpoint](checkpoints/2026-09-14-既存PJ移行スキル.md)
- [x] 2026-09-12 初期構成を /init-rules で立ち上げ → [checkpoint](checkpoints/2026-09-12-初期構成.md)
- [x] 2026-09-12 記録ルールの改訂4件と共通ルールの圧縮（5コミット、`9875334`〜`6f16ea0`）→ [README 経緯](README.md#経緯)
- [x] 2026-09-12 ADR節を廃止し、決定は`REQUIREMENTS.md`の方針・理由は`NOTES.md`へ → [checkpoint](checkpoints/2026-09-12-ADR節の廃止.md)
- [x] 2026-09-14 既存PJ向けのcheckpoint移行コマンドを追加（kakeiboで手作業の移行をして踏んだ罠を、テスト付きで固定）→ [checkpoint](checkpoints/2026-09-14-checkpoint移行コマンド.md)

## 進行中
(なし)

