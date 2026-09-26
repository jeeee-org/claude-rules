---
name: install-rules
description: claude-rulesの共通ルールをPJの`AGENTS.md`へ入れる・最新にする・取り除くのを、選択肢を案内しながら行う。読み手（Claude / Codex）と個人の運用（自動commit・自動push・worktree・ツール名）をPJごとに選ばせ、既存の`CLAUDE.md`は`AGENTS.md`へ移して統一する。複数のPJをまとめて最新にする、このPCへ道具（スキル・フック）を入れる、も扱う。「このPJにルールを入れて」「全PJのルールを最新にして」「ルールを入れて」「claude-rulesを更新して」などで使う。PJの記録ファイルの雛形作りはinit-rules。
---

# install-rules — 共通ルールを案内しながら入れる

利用者はスクリプトのオプションを覚えていない前提で、**選択肢を示して選んでもらい、コマンドはこちらで組み立てて実行する**。オプション名を利用者に覚えさせたり、打たせたりしない。

**前提（2026-09-26〜）**：共通ルールはグローバル（`~/.claude/CLAUDE.md`・`~/.codex/AGENTS.md`）に入れない。**各PJの`AGENTS.md`の先頭に書き込み**、PJ固有の指示はその下に書く。PJのルールファイルは`AGENTS.md`に統一し、`CLAUDE.md`は置かない（Claude Codeはv2.1.277以降`AGENTS.md`を直接読む）。PJ単体で配っても相手に同じルールが効く。

**問い方**：Claude CodeならAskUserQuestionで選択肢を出す（各選択肢に「誰向けか・何が変わるか」を1行添える）。使えない環境（Codex等）では、番号付きの選択肢を出して答えを待つ。**推奨がある時は先頭に置いて「（推奨）」を付ける。**

## 0. 道具の場所

次の順に探し、見つかったcloneのルートを`$clone`とする。

1. いまの作業ディレクトリが`rules/common-rules.md`と`tools/embed-rules.py`を持つ → そこ
2. `dirname "$(readlink -e ~/.claude/skills/init-rules/IMPROVEMENTS.md)"`（Codexなら`~/.codex/skills/init-rules/IMPROVEMENTS.md`）
3. どちらも無い → cloneしてよいか、置き場所をどこにするかを聞いてから`git clone https://github.com/jeeee-org/claude-rules.git <置き場所>`

`python3`が要る（`python3 --version`で確かめる。無ければ入れ方を案内して止まる）。正本を最新にするため、cloneで`git pull --ff-only`してから使う（clone自身で作業中なら不要）。

## 1. 何をするかを決める

利用者の言葉で決まっていれば聞かずに進む。

| やること | 言われ方の例 | 進む先 |
|---|---|---|
| 1つのPJに入れる・選び直す・取り除く | 「このPJにルールを入れて」「配る用に」 | 2 |
| 複数のPJをまとめて最新にする／まだのPJに入れる | 「全PJのルールを最新にして」「正本を直したので反映して」 | 3 |
| このPCへ道具（スキル・フック）を入れる | 「claude-rulesを入れて」「新しいPC」 | 4 |

新しいPCでは4のあと、PJに入っていなければ3へ続ける。

## 2. 1つのPJ

### 1) 対象と状態
- 対象のPJ（既定はいまの作業ディレクトリ。claude-rulesのclone自身なら、どのPJかを聞く。claude-rules自身も対象にしてよい）。
- `python3 "$clone/tools/embed-rules.py" --scan <PJの親>`の該当行で状態を見て、日本語で伝える。
  - **書き込み済み** → 聞く：最新へ更新する（選択そのまま・推奨）／選び直す（2)・3)へ）／取り除く（`--remove`。消える物を先に伝えて確認を取る）。更新は`python3 "$clone/tools/embed-rules.py" <PJ>`
  - **未書き込み** → 2)・3)へ

### 2) 読み手（初回・選び直し）
| 選択肢 | 渡すもの |
|---|---|
| ClaudeとCodexの両方（推奨） | `--target both`：`AGENTS.md`に書く。`CLAUDE.md`があれば`AGENTS.md`へ移して統一する（下の4)） |
| Claudeだけ | `--target claude`：`CLAUDE.md`に書く |
| Codexだけ | `--target codex`：`AGENTS.md`に書く |

### 3) 個人の運用（初回・選び直し）
**選択肢は`python3 "$clone/tools/embed-rules.py" --list-options`の出力から作る**（ここに書き写さない。正本は道具の側）。複数選択で聞き、選ばなかった時に代わりに入る決まり（例：pushはユーザーの指示があった時だけ）も添える。1つも選ばないのも可（`--options none`）。利用者自身のPJなら「全部（いつもの運用）」を推奨にしてよい（`--options all`）。

あわせて、**選択ではなく常に入るもの**（一覧の最後の行）を1行で伝える。外したいと言われても外さない——全版で必須と決めてある。

### 4) 実行
1. `--dry-run`を付けて変わるファイルを見せる。`both`でPJに`CLAUDE.md`があれば`--absorb-claude-md`を付ける（`CLAUDE.md`のPJ固有の指示を`AGENTS.md`のブロックの下へ移し、`CLAUDE.md`を消す）。
   `python3 "$clone/tools/embed-rules.py" <PJ> --target <先> --options <カンマ区切り|none|all> [--absorb-claude-md] --dry-run`
2. 本実行する。
3. **`--absorb-claude-md`が出した「機械で置き換えなかった行」を1行ずつ直す。** 「グローバル」「CLAUDE.md」がまだ残っている行で、共通ルールやこのファイルを指しているなら「共通ルール」「`AGENTS.md`」へ。別の意味（グローバルホットキー、環境変数をグローバルに置く、Claude Codeという製品の話）ならそのまま。**PJ固有の指示の中身は変えない**（言い回しの置き換えだけ）。
   **`AGENTS.md`の外にも残っていないかを見る**：`git grep -n 'グローバル *§\|グローバル *`~/.claude\|グローバル既定' -- ':!checkpoints' ':!docs/checkpoints'`。PJのスクリプトのコメントやPJ固有のスキルに「グローバル§5」等が残っていることがある（道具は`AGENTS.md`しか直さない）。直すのは言い回しだけ。過去の記録（checkpoint等）は事実なので直さない。ループ等が実行中なら止まっている時に直す。
4. 元から`AGENTS.md`に中身があった場合（Next.jsの注意書き、Codex向けのPJ指示など）は、移した`CLAUDE.md`の中身の後ろに残る。**同じことを2回言っていないか**を見て、重複していれば利用者に聞いてから片方にまとめる。
5. 出た`※`の知らせを日本語で伝える（例：このPCに以前のグローバルの共通ルールが残っている → 4の`install.sh`で外れる）。
6. `<PJ>/.claude-rules/check-limits.sh <PJ>`で上限を見る（共通ルールのブロックと、PJ固有の部分を分けて測る）。
7. commitはPJのGit運用に従う。導入そのものは利用者の確認を取ってからcommitする。コミットメッセージは「共通ルールをAGENTS.mdへ書き込み、CLAUDE.mdを統一する」の趣旨で、記録の関門があるPJでは末尾に`記録なし: 共通ルールの書き込み（claude-rulesの配布の変更）`を付けてよい。

## 3. 複数のPJをまとめて

1. `python3 "$clone/tools/embed-rules.py" --scan <PJを並べた場所>`で一覧を出し、状態ごとに数えて伝える（最新／古い／未書き込み／`CLAUDE.md`が残っている）。
2. **古い**ものは、前回の選択のまま`python3 "$clone/tools/embed-rules.py" <PJ>`で最新にする（聞き直さない）。
3. **未書き込み**のものは、まとめて聞く：同じ読み手・同じ個人の運用で全部に入れるか（利用者自身のPJなら「両方・全部」を推奨）、PJごとに選ぶか。そのあと2の4)を1つずつ行う。
4. どのPJも、書き込む前に`git status`が綺麗かを見る。未commitの変更があるPJは飛ばし、最後に一覧で伝える（無関係な変更を混ぜない）。
5. commitとpushは各PJのGit運用に従う（`pushはユーザー指示時のみ`のPJはcommitまで）。

## 4. このPCへ道具を入れる（`install.sh`）

スキル（`init-rules` / `migrate-rules` / `install-rules`）と、記録の関門・AI署名の関門、上限の判定を配る。**共通ルールは入れない**。以前の版がグローバルへ入れた共通ルールのブロックがあれば取り除く。

次の3つを聞く（まとめて1回で聞いてよい）。

| 聞くこと | 選択肢 | 渡すもの |
|---|---|---|
| Codexにも入れるか | 入れる（推奨。Codexを使うなら）／入れない | 入れないなら`--no-codex` |
| 記録の関門とAI署名の関門を`~/.claude/settings.json`に登録するか | 登録する（推奨。控えを取る）／登録しない | しないなら`--no-hook-register` |
| 表示の設定（思考の要約・focus表示）を足すか | 足す（推奨。無いキーだけ）／足さない | 足さないなら`--no-display-settings` |

**グローバルに以前の共通ルールが残っていて、このPCのPJにまだ書き込んでいない時**は、先に3でPJへ書き込むことを勧める（先に外すと、書き込むまでの間ルールの無いPJが出る）。どうしても先に道具を入れるなら`--keep-global-rules`（ブロックを残す。PJへ書き込んだら付けずにもう一度実行する）。

`cd "$clone" && ./install.sh <選んだもの>`を実行し、Claude Codeの再起動か`/reload-skills`が要ることを伝える。

## 注意
- 道具が出したエラーや警告は言い換えずに要点を伝える。初回に`--options`を渡し忘れると道具が止まる（黙って既定を入れないため）。
- 案内の途中でズレや足りない選択肢に気づいたら、claude-rulesの`IMPROVEMENTS.md`へ書く（`init-rules`の「改善案の記録」と同じ手順）。
