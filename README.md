# claude-rules

Claude Code の**グローバル共通ルール**（`~/.claude/CLAUDE.md` の本体：4軸 + checkpoint の進行管理・Git 既定・memory 不使用・スキル化ルール・常時ロード数値上限）と **`/init-rules` スキル**を、複数PCへ配布・同期するためのリポジトリ。

[quorum](https://github.com/jeeee-org/quorum) / [cadence](https://github.com/jeeee-org/cadence) と同じ **install.sh + マーカーブロック方式**。3リポを入れると `~/.claude/CLAUDE.md` は次の3ブロック構成になる：

```
<!-- claude-rules:begin -->   … 共通骨格 §1〜7（このリポが正本）
<!-- quorum-triage:begin -->  … quorum トリアージ（quorum リポが正本）
<!-- cadence-triage:begin --> … cadence トリアージ（cadence リポが正本）
```

## インストール（新PC）

```bash
git clone git@github.com:jeeee-org/claude-rules.git
cd claude-rules && ./install.sh
```

続けて quorum → cadence の順に各リポの `install.sh` を実行すると、CLAUDE.md の並びが揃う（順不同でも動作はする。マーカー置換なので再実行は冪等）。

## 構成

| パス | 役割 |
|---|---|
| `rules/global-rules.md` | **正本**。`~/.claude/CLAUDE.md` の claude-rules ブロックに注入される共通骨格（§1 進行管理 / §2 checkpoint 方式・数値上限 / §3 進行ルール / §4 書き分け / §5 Git / §6 memory 不使用 / §7 PJ側 CLAUDE.md の書き分け） |
| `skills/init-rules/` | **正本**。新規/既存PJに 4軸 + checkpoint 構成を立ち上げるスキル。`~/.claude/skills/init-rules` へコピーされる |
| `install.sh` | 上記2つを配置。ブロックはマーカー間置換（無ければ末尾追記）。配置後に CLAUDE.md の 14KB 上限を目安チェック |

## ルールを変更するとき

1. **このリポの `rules/global-rules.md`（または `skills/init-rules/SKILL.md`）を編集する**。`~/.claude/CLAUDE.md` のブロック内を直接編集しない（次回 install で消える）
2. `./install.sh` でローカルに反映
3. commit / push
4. 他のPCでは `git pull && ./install.sh`

## 経緯

- 2026-06-17: グローバル `~/.claude/CLAUDE.md` と `/init-rules` を作成（当初は版管理外）
- 2026-07-10: Hermes Agent 調査の応用でルール3点を追加（常時ロード数値上限／スキル化の前向き自問／スキル diff 承認・使用後自己改善）したのを機に、本リポへ切り出して配布可能化
