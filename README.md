# claude-rules

Claude Code と Codex の**グローバル共通ルール**、および各環境の `init-rules` スキルを複数PCへ配布・同期するためのリポジトリ。LLM固有の指示面は `~/.claude/CLAUDE.md` と `~/.codex/AGENTS.md` に分離し、4軸 + checkpoint のPJ文書は共有する。

[quorum](https://github.com/jeeee-org/quorum) / [cadence](https://github.com/jeeee-org/cadence) と同じ **install.sh + マーカーブロック方式**。3リポを入れると `~/.claude/CLAUDE.md` は次の3ブロック構成になる：

```
<!-- claude-rules:begin -->   … 共通骨格 §1〜8（このリポが正本）
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
| `rules/global-rules.md` | **正本**。`~/.claude/CLAUDE.md` の claude-rules ブロックに注入される共通骨格（§1 進行管理 / §2 checkpoint 方式・数値上限 / §3 進行ルール / §4 書き分け / §5 Git / §6 memory 不使用 / §7 PJ側 CLAUDE.md の書き分け / §8 外部文面で Markdown 不使用） |
| `rules/codex-global-rules.md` | **Codex用の独立した正本**。`~/.codex/AGENTS.md` の codex-rules ブロックへ注入 |
| `skills/init-rules/` | **正本**。新規/既存PJに 4軸 + checkpoint 構成を立ち上げるスキル。`~/.claude/skills/init-rules` へコピーされる |
| `skills/codex-init-rules/` | Codex版。`~/.codex/skills/init-rules` へコピーされ、PJ固有指示は `AGENTS.md` に生成する |
| `skills/codex-triage/` | 「トリアージして」等の自然言語で発動するCodex版明示トリアージスキル |
| `hooks/triage-classifier.sh` | **正本**。UserPromptSubmit フック：プロンプトを haiku がヘッドレス分類（T0/T1/T2a/CADENCE）し、T0 以外のときだけ判定をコンテキスト注入する。quorum/cadence トリアージの発動漏れ対策（判断をメインモデルの自己申告から独立させる）。`~/.claude/hooks/` へコピーされ、settings.json への登録は **opt-in**（install.sh が案内を表示。+2〜6秒/プロンプト） |
| `hooks/triage-rubric.txt` | **分類基準の唯一の正本**。Claudeフック、Codexラッパー、Codex `triage` スキルで共有 |
| `hooks/codex-triage.sh` | Codexの初回プロンプトを `gpt-5.4-mini` で分類する起動ラッパー。`~/.codex/hooks/codex-triage` へ配置 |
| `tools/check-limits.sh` | **正本**。常時ロードされるファイルのサイズ上限（グローバル §2）を機械判定する。グローバル CLAUDE.md / AGENTS.md に加え、**PJ の CLAUDE.md 6,144B と PROGRESS.md の 60行かつ 12,288B も見る**。`~/.claude/tools/` `~/.codex/tools/` へコピーされ、`install.sh` 末尾と §2 の両方から呼ばれる。上限は `CR_LIMIT_*` 環境変数か、PJ の `.claude/limits.env` で上書き可（グローバル §2「PJ の CLAUDE.md で上書き可」の機械可読版） |
| `tools/collect-state.sh` | 複数PC間のズレを採取する。正本のハッシュ・正本と生成物のドリフト diff・ブロック構成・配置物一覧を1回で出す。**push 権限の無いPCで実行して出力を貼る**用途。subtree 配下でも動く |
| `install.sh` | 上記を両環境へ配置。ブロックはマーカー間置換（無ければ末尾追記）。配置後に `tools/check-limits.sh` で上限を目安チェック。`--no-codex` で Codex 側の配置を省ける |

`install.sh` は両方を既定で配置する。配置先は `CLAUDE_CONFIG_DIR` / `CODEX_HOME` で変更でき、再実行は冪等。
Codex をメインエージェントに使わないPCでは `./install.sh --no-codex`（または `CLAUDE_RULES_INSTALL_CODEX=0`）で Codex 側の配置を丸ごと省ける。`AGENTS.md` は quorum / cadence も注入するため、それらを止めない限りファイル自体は残る（省けるのは claude-rules 分だけ）。
CLIのインストール有無ではスキップしない。新PCへの設定の事前配布を可能にするため、Claude CodeまたはCodexが未導入でも対応する設定ディレクトリを作成する。

Codex 0.144.1 の安定版hooksには、Claude Codeの `UserPromptSubmit` に相当する各ターンイベントがない。そのためCodex版は初回プロンプトだけを分類する明示的な起動ラッパーとしている。

```bash
~/.codex/hooks/codex-triage -- "調査・実装してほしい内容"
```

分類子プロセスは `--ephemeral --ignore-user-config` で起動し、再帰とセッション保存を避ける。モデルは `CODEX_TRIAGE_MODEL`、タイムアウトは `CODEX_TRIAGE_TIMEOUT` で上書きできる。分類失敗時は通常のCodex起動へフォールバックする。

独立モデルでの事前分類が不要なら、通常のCodex会話で「この依頼をトリアージしてから進めて」と自然言語で指定できる。グローバル `AGENTS.md` が `$triage` を必須発動し、ユーザーが内部コマンドを覚える必要はない。この経路ではメインCodex自身が分類する。実行依頼がT1なら、Codex版 `$quorum` がインストール済みの場合は提案だけで止めず、そのまま利用する。

## ルールを変更するとき

1. **このリポの `rules/global-rules.md`（または `skills/init-rules/SKILL.md`）を編集する**。`~/.claude/CLAUDE.md` のブロック内を直接編集しない（次回 install で消える）
2. `./install.sh` でローカルに反映
3. commit / push
4. 他のPCでは `git pull && ./install.sh`

## 経緯

- 2026-06-17: グローバル `~/.claude/CLAUDE.md` と `/init-rules` を作成（当初は版管理外）
- 2026-07-10: Hermes Agent 調査の応用でルール3点を追加（常時ロード数値上限／スキル化の前向き自問／スキル diff 承認・使用後自己改善）したのを機に、本リポへ切り出して配布可能化
