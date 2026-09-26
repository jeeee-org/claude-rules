---
name: install-rules
description: claude-rulesの共通ルールを入れる・更新する・取り除くのを、選択肢を案内しながら行う。「このPCの全PJに入れる（グローバル）」か「1つのPJへ書き込む（PJ単体で配る・Codexで使う・グローバルを入れられない相手）」かを選ばせ、PJへ書き込む時は読み手と個人の運用をPJごとに選ばせてから道具を実行する。「ルールを入れて」「共通ルールをこのPJに入れて」「claude-rulesを更新して」「配る用にルールを書き込んで」などで使う。PJの記録ファイルの雛形作りはinit-rules。
---

# install-rules — 共通ルールを案内しながら入れる

利用者はスクリプトのオプションを覚えていない前提で、**選択肢を示して選んでもらい、コマンドはこちらで組み立てて実行する**。オプション名を利用者に覚えさせたり、打たせたりしない。

**問い方**：Claude CodeならAskUserQuestionで選択肢を出す（各選択肢に「誰向けか・何が変わるか」を1行添える）。使えない環境（Codex等）では、番号付きの選択肢を出して答えを待つ。**推奨がある時は先頭に置いて「（推奨）」を付ける。**

## 0. 道具の場所

次の順に探し、見つかったcloneのルートを`$clone`とする。

1. いまの作業ディレクトリが`rules/common-rules.md`と`tools/embed-rules.py`を持つ → そこ
2. `dirname "$(readlink -e ~/.claude/skills/init-rules/IMPROVEMENTS.md)"`（Codexなら`~/.codex/skills/init-rules/IMPROVEMENTS.md`）
3. どちらも無い → cloneしてよいか、置き場所をどこにするかを聞いてから`git clone https://github.com/jeeee-org/claude-rules.git <置き場所>`

`python3`が要る（`python3 --version`で確かめる。無ければ入れ方を案内して止まる）。

## 1. 入れ方を選ぶ

| 選択肢 | 向いている人 | 何が起きるか |
|---|---|---|
| このPCの全PJに入れる（グローバル） | claude-rulesをこのPCに置ける人 | `~/.claude/CLAUDE.md`（と`~/.codex/AGENTS.md`）へ共通ルールを入れ、スキル・フックも配る。**個人の運用は全部入り**で選べない |
| 1つのPJへ書き込む | PJ単体で配る相手／Codexで使うPJ／グローバルを入れられない人 | そのPJの`AGENTS.md` / `CLAUDE.md`の先頭に共通ルールを書き込む。**個人の運用をPJごとに選べる** |

利用者の言葉で決まっていれば聞かずに進む（「このPJに」「配る用に」ならPJ、「このPCに」ならグローバル）。個人の運用を選びたいと言われたら、PJへ書き込むほうだと伝える。

## 2A. グローバルに入れる

次の3つを聞く（まとめて1回で聞いてよい）。

| 聞くこと | 選択肢 | 渡すもの |
|---|---|---|
| Codexにも入れるか | 入れる（推奨。Codexを使うなら）／入れない | 入れないなら`--no-codex` |
| 記録の関門とAI署名の関門を`~/.claude/settings.json`に登録するか | 登録する（推奨。控えを取る）／登録しない | しないなら`--no-hook-register` |
| 表示の設定（思考の要約・focus表示）を足すか | 足す（推奨。無いキーだけ）／足さない | 足さないなら`--no-display-settings` |

`cd "$clone" && ./install.sh <選んだもの>`を実行し、最後に出るサイズの判定（`✓` / `△` / `⚠`）と、Claude Codeの再起動か`/reload-skills`が要ることを伝える。

## 2B. 1つのPJへ書き込む

### 1) 対象と状態
- 対象のPJ（既定はいまの作業ディレクトリ。claude-rulesのclone自身なら、どのPJかを聞く）。
- `grep -l 'claude-rules:embed:begin' <PJ>/AGENTS.md <PJ>/CLAUDE.md`で書き込み済みかを見る。書き込み済みなら、マーカー行の`embed-<先> / 選択 <運用>`を読んで、いまの状態を日本語で伝えてから聞く：
  - 最新へ更新する（選択そのまま・推奨）→ `python3 "$clone/tools/embed-rules.py" <PJ>`
  - 選び直す → 2)・3)へ
  - 取り除く → `--remove`（消える物を先に伝えて確認を取る）

### 2) 読み手（初回・選び直し）
| 選択肢 | 渡すもの |
|---|---|
| ClaudeとCodexの両方（推奨） | `--target both`：PJのルールを`AGENTS.md`に統一する（Claude Codeはv2.1.277以降が直接読む）。`CLAUDE.md`は作らない。既にある時だけ先頭に`@AGENTS.md`を足して繋ぐ |
| Claudeだけ | `--target claude`：`CLAUDE.md`に書く |
| Codexだけ | `--target codex`：`AGENTS.md`に書く |

### 3) 個人の運用（初回・選び直し）
**選択肢は`python3 "$clone/tools/embed-rules.py" --list-options`の出力から作る**（ここに書き写さない。正本は道具の側）。複数選択で聞き、選ばなかった時に代わりに入る決まり（例：pushはユーザーの指示があった時だけ）も添える。1つも選ばないのも可（`--options none`）。

あわせて、**選択ではなく常に入るもの**（一覧の最後の行）を1行で伝える。外したいと言われても外さない——全版で必須と決めてある。

### 4) 実行
1. `python3 "$clone/tools/embed-rules.py" <PJ> --target <先> --options <カンマ区切り|none> --dry-run`で変わるファイルを見せる。
2. そのまま本実行し、出た`※`の知らせを日本語で伝える。
   - **二重に読まれる**：このPCのグローバルにも入っている。配る用のブランチやコピーで書き込むのが素直だと伝える。
   - **CLAUDE.mdにPJ固有の指示がありCodexに届かない**：`AGENTS.md`のブロックの下へ移すかを聞く。移すなら原文のまま移し、そのあと`CLAUDE.md`を消して`AGENTS.md`だけに統一するか（推奨）、`@AGENTS.md`の行だけ残すか（Claude Codeがv2.1.277より古い相手がいる時）を聞く。
3. `<PJ>/.claude-rules/check-limits.sh <PJ>`で上限を見る。
4. commitはしない。変わったファイル（`AGENTS.md` / `CLAUDE.md` / `.claude-rules/`）を示し、commitするかを聞く（選んだ運用に「commitを指示を待たずに行う」があっても、導入自体は利用者の確認を取る）。

## 3. 更新だけ（2回目以降）

「ルールを最新にして」と言われたら、グローバルなら`cd "$clone" && git pull --ff-only && ./install.sh`（前回と同じ指定を聞き直さなくてよい。変えたいと言われた時だけ2Aへ）。PJなら`python3 "$clone/tools/embed-rules.py" <PJ>`だけで、前回の読み手と選択を引き継ぐ。`--check`で古いかどうかだけを見ることもできる。

## 注意
- 道具が出したエラーや警告は言い換えずに要点を伝える。初回に`--options`を渡し忘れると道具が止まる（黙って既定を入れないため）。
- 案内の途中でズレや足りない選択肢に気づいたら、claude-rulesの`IMPROVEMENTS.md`へ書く（`init-rules`の「改善案の記録」と同じ手順）。
