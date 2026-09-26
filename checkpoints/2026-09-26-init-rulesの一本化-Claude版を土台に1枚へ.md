# 2026-09-26 init-rulesの一本化 — Claude版を土台に1枚へ

## 依頼
`init-rules`のClaude版とCodex版の2枚の正本を1枚にする。PJのルールファイルが`AGENTS.md`に統一され、作るものが同じになったため、正本を分けておく理由が無くなった。

## やったこと
- `skills/init-rules/SKILL.md`（Claude版・雛形入り）を土台にした。Codex版（散文）の中身は、このファイルに全部含まれていた。
- Claude専用の書き方をどちらでも通じる書き方へ直した。
  - 日付：システムリマインダの`currentDate`を見る → 会話に渡された日付、無ければ`date +%F`
  - cloneの場所と改善メモの置き場：`~/.claude/...`だけ → Codexの`~/.codex/...`も併記
  - 雛形中の`/init-rules` → `init-rules`（呼び方の記号を付けない）
  - 確認のしかた：選択肢の画面が使えればそれで、無ければ番号付き（冒頭に1段落）
  - 最後のpush：「PJに止める明示がある時だけ止める」 → 「共通ルールで自動pushを選んでいればpush、でなければ聞く」（個人の運用の選択に合わせた。Codex版の「明示的に許可した場合だけ」と同じ結果になる）
- `skills/codex-init-rules/`を削除。`install.sh`はCodex側にも`skills/init-rules`をコピーする（改善メモのsymlinkは両方に張ったまま）。
- README構成表、`tools/collect-state.sh`、このリポの`AGENTS.md`（スキルは1スキル1枚）、`REQUIREMENTS.md`（統一の要求のC案を実施済みに、関連する未決を整理）を追従。

## 確かめたこと
- `./install.sh`後、`~/.claude/skills/init-rules/SKILL.md`と`~/.codex/skills/init-rules/SKILL.md`が同一。Codex側の改善メモのsymlinkも解決する。
- Claude（`claude -p`）で空のリポに`init-rules`を使わせ、`AGENTS.md`（共通ルールのブロック＋PJ固有）・`REQUIREMENTS.md`・`PROGRESS.md`・`NOTES.md`・`checkpoints/<今日>-初期構成.md`・`.claude-rules/check-limits.sh`が作られ、commitまで行われた。
- Codexでの実走は、モデル指定のエラー（ChatGPTアカウントでは既定のモデルも指定したモデルも使えない）で確かめられなかった。2026-09-20と同じ。Codex側は同じファイルがコピーされたことの確認まで。
