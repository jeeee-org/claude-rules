# claude-rules

Claude CodeとCodexの**共通ルール**（4軸 + checkpointの記録・進行・Git・文面の決まり）と、それを入れる道具・スキルを配るリポジトリ。

**共通ルールは各PJの`AGENTS.md`の先頭に書き込む**（2026-09-26〜。それまでは`~/.claude/CLAUDE.md`・`~/.codex/AGENTS.md`へ注入していた）。PJ単体で配ることが増えたため、重複を避けるより**PJだけで完結すること**を取った。重複した写しは正本（`rules/common-rules.md`）からの生成物なので、手で保守しない。

```
<PJ>/AGENTS.md
  <!-- claude-rules:embed:begin (版 … / embed-both / 選択 …) -->  … 共通ルール§1〜9（このリポが正本）
  <!-- claude-rules:embed:end -->
  # AGENTS.md — <PJ>                                              … PJ固有の指示（手で書く）
```

PJのルールファイルは`AGENTS.md`に統一し、`CLAUDE.md`は置かない（Claude Codeはv2.1.277以降`AGENTS.md`を直接読む）。

## インストール（新PC）

**AIに頼む**：cloneしたこのリポでClaude Code / Codexを開いて「ルールを入れて」と言う。リポの`.claude/skills/`・`.agents/skills/`から`install-rules`スキルが見え、道具の導入（`install.sh`）とPJへの書き込みを選択肢で案内する。オプションを覚える必要は無い。

```bash
git clone git@github.com:jeeee-org/claude-rules.git
cd claude-rules && ./install.sh          # 道具（スキル・フック・判定）だけ。共通ルールは入れない
python3 tools/embed-rules.py --scan ~/Develop   # PJごとの共通ルールの状態
```

quorumを使うPCでは続けてquorumの`install.sh`も実行する（順不同。マーカー置換なので再実行は冪等）。

## 構成

| パス | 役割 |
|---|---|
| `IMPROVEMENTS.md` | **改善案メモの正本**。共通ルール・配布の仕組みについて使いながら気づいたことを溜める。`install.sh`がClaude / Codex両方の`skills/init-rules/IMPROVEMENTS.md`からここへsymlinkを張るので、**実行時の追記はそのままgit管理下のこのファイルへ入り、再インストールの`rm -rf`でも消えない**。並びは古い順・末尾追記（他PCのcloneとのmergeが素直になる）。quorumと同じ方式 |
| `rules/common-rules.md` | **共通ルールの唯一の正本**。読み手ごとに違う語は`{{名前}}`、片方にだけ要る文・選べる個人の運用は`<!-- if:条件 -->…<!-- endif -->`で書く（条件の印は`claude` / `codex`と個人の運用の名前。`,`＝または・`+`＝かつ・`!`＝でない）。中身は§1進行管理 / §2 checkpoint方式・数値上限 / §3進行ルール / §4書き分け / §5 Git / §6 memory不使用 / §7 PJ側の書き分け / §8外部文面でMarkdown不使用 / §9応答の書き方 |
| `tools/build-rules.py` | 正本から版の本文を作る（`--variant embed-both|embed-claude|embed-codex`、`--options`）。個人の運用の一覧（`OPTIONS`）の正本もここ |
| `tools/embed-rules.py` | 共通ルールを**PJの`AGENTS.md`へ書き込む**。個人の運用をPJごとに選び、`CLAUDE.md`を`AGENTS.md`へ移して統一し、配下のPJの状態を一覧にする。使い方は「PJへ共通ルールを書き込む」 |
| `skills/install-rules/` | **正本**。PJへの共通ルールの書き込み・まとめての更新・道具の導入を、選択肢で案内しながら行うスキル。`~/.claude/skills/`と`~/.codex/skills/`へコピーされ、リポの`.claude/skills/`・`.agents/skills/`からもsymlinkで見える（cloneしただけで使える） |
| `skills/init-rules/` | **正本**（Claude・Codex共通の1枚。2026-09-26にCodex版を統合）。新規PJに共通ルールを書き込み、4軸 + checkpoint構成を立ち上げるスキル。`~/.claude/skills/init-rules`と`~/.codex/skills/init-rules`へ同じものがコピーされる |
| `skills/migrate-rules/` | **正本**。既存PJを記録ルールの改訂（2026-09-12〜）に揃えるスキル。checkpointの移動と改名・`REQUIREMENTS.md`の新設と進行中の作業カードの立ち上げ・決定/未決/ADRの振り分け・`NOTES.md`の整理・PJの`CLAUDE.md`の書き直しを、ユーザーの判断を挟みながら何も落とさずに行う。**過去の「次にやること」から落ちた作業を拾う**手順を含む。判断の要らない部分は`tools/migrate-checkpoints.py`・`tools/check-moved-lines.py`・`tools/fix-spacing.py`を呼ぶ（cloneの場所は`init-rules`の`IMPROVEMENTS.md`のsymlinkから辿る）。`~/.claude/skills/migrate-rules`へコピーされる。Codex版は無い |
| `skills/codex-triage/` | 「トリアージして」等の自然言語で発動するCodex版明示トリアージスキル。**ユーザーが言った時だけ**動く（`AGENTS.md`からの必須発動は2026-09-15に廃止） |
| `hooks/triage-classifier.sh` | **正本**。UserPromptSubmitフック：プロンプトをhaikuがヘッドレス分類（T0/T1/T2a）し、T0以外のときだけ判定をコンテキスト注入する。quorumトリアージの発動漏れ対策（判断をメインモデルの自己申告から独立させる）。`~/.claude/hooks/`へコピーされ、settings.jsonへの登録は**opt-in**（install.shが案内を表示。+2〜6秒/プロンプト） |
| `hooks/commit-record-guard.sh` | **正本**。PreToolUse（Bash）フック：commitしようとした時に、`REQUIREMENTS.md` / `PROGRESS.md` / `NOTES.md` / `checkpoints/`のどれかが一緒に変わっているかを見る。1つも無ければ**commitを止めて差し戻す**（共通ルール§3「タスク完了時（必須）」の抜けを、私の自己申告から独立して捕まえる）。禁止ではなく意識した判断の強制で、要らない時は理由を述べて`CR_SKIP_RECORD_GUARD=1`を付けて通す（コマンドに残るので後から分かる）。`--amend`・`--dry-run`、記録の方式を使っていないリポ、gitの外、`jq`も`python3`も無い環境は黙って通す（fail-open）。`CLAUDE.md`は数えない（ルールだけを直したcommitも記録は要る）。見るリポは**`git -C <パス>`＞先頭の`cd`＞セッションのカレント**の順に決める（gitの実際の挙動と同じ。`-C`が変数などで解けない時は判定しない）。**判定できるのは「編集は前の呼び出しで済ませ、この呼び出しはcommitだけ」の形に限られる**——`PreToolUse`は実行前に走るので、同じ呼び出しで書いてからcommitする形では書き込みがまだ無い。その形は判定せず「分けて打つ」ことを求める。**ヒアドキュメントは本体だけを落とす**（`<<`から後ろを全部切ると、その後ろのcommitが検出から漏れて素通りする）。**書き込みの検出は引用符の中身を落としてから行う**——`git commit -m "…<noreply@anthropic.com>" && git push`の`m>`と閉じ引用符をリダイレクトと読んで誤検知していた（2026-09-20）。**誤検知そのものより逃げ道が問題**で、止められた側が`-m`をやめて`-F ファイル`へ回った結果、そのcommitは関門を素通りした。止めた時は**コマンド全体が実行されない**ので、差し戻しの文面でそう告げる。**`install.sh`が`~/.claude/settings.json`へ登録するので既定で有効**（控えは`settings.json.bak`。`--no-hook-register`で止められる）。**効いているかは`tools/check-record-guard.sh --repo <リポ>`で、作業するリポごとに確かめる。** このフックは呼ばれるたびに`~/.claude/.record-guard-seen`へ時刻を書くので、**配線が生きているかを手で試さなくても読める**（後追いのフックが「入口が最後に呼ばれたのは何分前か」を添える）。記録の抜けを最後に捕まえるのは`hooks/push-record-guard.sh`で、ここは早く気づくための入口テストは`python3 -m unittest discover -s tools/tests` |
| `hooks/push-record-guard.sh` | **正本・記録の関門の本丸**。PreToolUse（Bash）フック：pushしようとした時に、**これから押し出すcommit**（`HEAD --not --remotes`。マージは除く）を1つずつ見て、記録の入っていないものがあれば止める。**commitは既にあるので、コマンドの書き方に一切依存せず正確に判定でき、しかもまだ止められる**——commitの時点は、実行前で書き込みが見えず（入口）／既にできていて止められない（後追い）という、判定の情報が揃わない唯一の時点だった。例外は**コミットメッセージのトレーラ**`記録なし: <理由>`（英語は`No-Record:`）で、コマンドに書く指定と違い**理由が履歴に残って後から数えられる**。押し出す数が既定20件を超える時（作りたてのリポの初回pushなど）・リモートが無い・記録の方式を使っていないリポでは黙る（`CR_PUSH_MAX_COMMITS`で変更可） |
| `hooks/push-attribution-guard.sh` | **正本**。PreToolUse（Bash）フック：pushしようとした時に、**これから押し出すcommit**のメッセージを1本ずつ見て、AI帰属行（`Co-Authored-By: Claude …` / `🤖 Generated with …` / `noreply@anthropic.com`）が入っていれば止める。共通ルール§5.2禁止②を、私の自己申告から独立して担保する——**セッション側から「commitの末尾に付けよ」という指示が渡ることがあり**、規約が勝つ側だが、その判断を私に委ねている限り取りこぼす（2026-09-20に業務リポで実際に押してしまい、共有ブランチのforce pushで手当てした）。**なぜpushの時点か**は記録の関門と同じ——commitの時点はメッセージの渡し方（`-m` / `-F` / エディタ / ヒアドキュメント）に依存して中身が見えないが、pushの直前ならcommitはもう存在するので確実に読め、しかもまだ`--amend`で直せる（未pushなのでforceが要らない）。**署名の形をしたものだけを見る**（本文に「Claude」と書くこと自体は止めない）。**例外はコマンド側の`CR_SKIP_ATTRIBUTION_GUARD=1`だけで、メッセージのトレーラでは抜けられない**——問題にしているのがメッセージそのものなので、そこに例外を置くと堂々巡りになる（記録の関門とはこの点が違う）。記録の関門と違い**リポの作りで対象を絞らない**（規約は全リポに効く）。押し出す数が既定50件超・リモートが無い・gitの外では黙る（fail-open）。テストは`python3 -m unittest discover -s tools/tests` |
| `hooks/commit-record-audit.sh` | **正本**。PostToolUse（Bash）フック：**できてしまったcommitを後から見る網**。直前の呼び出しでcommitができていたら、`git show --name-only HEAD`を見て記録が入っているかを確かめ、無ければ知らせる。**止められない**（commitは既にある）が、**コマンドの書き方によらずgitの履歴そのものを見る**ので、入口が判定できなかった分の見逃しが残らない。直近120秒以内にできたcommitだけを見る（`CR_AUDIT_FRESH_SECONDS`で変更可）。`install.sh`が`PostToolUse`へ登録する |
| `tools/check-record-guard.sh` | **正本**。記録の関門が**いま効いているか**を確かめる。①スクリプトの判定が正しいかを使い捨てのリポでその場で見て、②**`--repo`で指した「これから作業するリポ」で発火するか**を試すコマンドを出す。②は`PreToolUse`を通さないと分からないので、出たコマンド（`CR_RECORD_GUARD_PROBE=1 git -C <リポ> commit --dry-run`）をBashツールで実行する。**フックはこの印を見たら状態にかかわらず必ず止める**ので、呼ばれているかだけが分かる。`--dry-run`なので、呼ばれなくても何もコミットされない。**登録は正しいのに、同じセッションの同じ階層でもリポによって発火する／しないが割れる**（条件は未特定）ため、**作業するリポが変わったらそのつど回す**。`~/.claude/tools/`へ配置 |
| `hooks/triage-rubric.txt` | **分類基準の唯一の正本**。Claudeフック、Codexラッパー、Codex `triage`スキルで共有 |
| `hooks/codex-triage.sh` | Codexの初回プロンプトを`gpt-5.4-mini`で分類する起動ラッパー。`~/.codex/hooks/codex-triage`へ配置 |
| `tools/check-limits.sh` | **正本**。常時ロードされるファイルのサイズ上限（共通ルール§2）を機械判定する。**PJの`AGENTS.md`は共通ルールのブロック（14,336B）とPJ固有の部分（6,144B）を分けて測り**、PROGRESS.mdの60行かつ12,288Bも見る。グローバルのファイル（`~/.claude/CLAUDE.md`等）の大きさと、以前の共通ルールの残り（二重読み込み）も出す。各PJの`.claude-rules/`へ`embed-rules.py`が複製し、共通ルール§2から呼ばれる（`~/.claude/tools/` `~/.codex/tools/`にも置かれる）。**各行に残量を出し、残りが`CR_WARN_MARGIN_BYTES`（既定512B）/ `CR_WARN_MARGIN_LINES`（既定5行）を切ったら`△`を付ける**（超過ではないのでexitは0のまま）。上限は`CR_LIMIT_*`環境変数か、PJの`.claude/limits.env`で上書き可（共通ルール§2「PJのCLAUDE.mdで上書き可」の機械可読版） |
| `tools/collect-state.sh` | 複数PC間のズレを採取する。正本のハッシュ・PJごとの共通ルールの状態（`embed-rules.py --scan`）・グローバルのファイルに残るブロック・配置物一覧を1回で出す。**push権限の無いPCで実行して出力を貼る**用途。subtree配下でも動く |
| `tools/migrate-checkpoints.py` | 既存PJのcheckpointを、リポ直下の`checkpoints/YYYY-MM-DD-作業名-中身.md`の形へ揃える（2026-09-12・2026-09-18の改訂への追従用）。`plan`で対応表の下書き（見出しから名前の候補）を出す→人かClaudeが名前を埋める（作業名は`REQUIREMENTS.md`のカードの見出しと同じ語）→`apply`で`git mv`・見出しの差し替え・リンクの張り直し→`check`で旧パスの残りとリンク切れを検査。**入口は移動元を見て自動で決まる**——`docs/checkpoints/`に日付名があれば「移動と改名」、無くて`checkpoints/`に`YYYY-MM-DD.md`が残っていれば「改名だけ」（置き場だけ先に揃えたPJ向け）。リンク切れの検査はcheckpointへの参照だけでなく、**PJの中の`.md`から張られた相対リンク全部**（移動で行き先がずれた外向きのリンクが見つかる。リポの外を指すものは判断しない）。日付の無い旧ディレクトリへの言及（READMEの表・`.gitignore`のコメントなど）は、Markdown以外も含めて「確かめる」として出す（exitは変えない）。**commitはしない**。名前の決定とADRの仕分けは判断が要るので対象外。**配置はせず**、cloneから`python3 <clone>/tools/migrate-checkpoints.py`で呼ぶ。テストは`python3 -m unittest discover -s tools/tests` |
| `tools/fix-spacing.py` | 英数字と日本語の間の半角スペース（§9の「境目の空白」）を見つけて落とす。**既定は検査だけ**で、`--write`で直す。行頭のマーカー（見出し・箇条書き・番号・チェックボックス・引用）と、本文の頭の日付・章番号の直後は残し、コードフェンスの中とインラインコードの**中身**は触らない。境目の判定では印（`**`と`` ` ``）を**両側とも透かす**ので、`` `install.sh` を``や`）** へ`のような、grepの文字クラスでは拾えない形も直せる。**直さずに出すだけの「判断が要る候補」が2つ**——記法そのものを列挙している行（コード印が4つ以上並ぶ行。空白が項目の区切り）と、日本語のうしろに`(`で始まる英語の補足が続く形（`次の一手 (Top 3)`）。規則の悪い例を載せている行は`--keep RE`で守る（このリポなら`--keep '悪い例|でなく'`）。日本語同士の空白は§9の対象外なので触らない。**配置はせず**、cloneから`python3 <clone>/tools/fix-spacing.py`で呼ぶ。テストは上と同じ |
| `tools/check-moved-lines.py` | 文書を分けて移した後、元の文書の各行が移動先のどれかに残っているかを突き合わせる（`NOTES.md`の一回限りの記録をcheckpointへ移し、残す節だけ書き直した時など）。元は`--from HEAD:NOTES.md`のようにgitの版を直接読めるので、書き換え前の退避が要らない。段を下げて貼った見出しと、行頭の字下げの違いは同じとみなし、空行と区切り行は数えない。どこにも無い行を行番号付きで出す（exit 1）。**配置はせず**、`migrate-rules`スキルからcloneのパスで呼ぶ。テストは上と同じ |
| `templates/loop/` | **正本**。ループ系エージェントのひな型。`common/`（統括役`loop-conductor`・判断役`gate-judge`・状態を動かす`loopctl.py`・早止まりを捕まえるStop / SubagentStopフック・決定論ゲートの共通部品・判断役の結論を決定論へ昇格させる仕組み・完了条件とゲート設計の雛形）に、`dev/`（要件→設計→実装→テストの工程役4体と各工程のレビュー役4体・工程ごとのゲート）か`generic/`（工程をpipeline.jsonで自分で決める汎用の工程役とレビュー役）を重ねて使う。**配置はしない**——対象リポへ入れるのは`tools/loop-scaffold.py`。Opus 5.5公式の早止まり対策（文章だけの番の終わりを完了とみなさない・残りを名指しして続けさせる・続行は数回まで・走っている作業の戻りを待つ・常駐指示の例文）をそのまま部品にしてある。入れた後の使い方は入れた先の`.claude/loop/README.md` |
| `tools/loop-scaffold.py` | ループのひな型を対象リポへ入れる。`python3 <clone>/tools/loop-scaffold.py <対象リポ> --profile dev`（開発以外は`--profile generic`）。既にあるファイルは上書きせず（`--force`で上書き）、対象の`.claude/settings.json`へStop / SubagentStopフックを重複なく足す（控えは`.bak`、`--no-settings`で触らない）。何をどの版から入れたかを`.claude/loop/.scaffold.json`に残す。**入れた先を新しい版へ上げるのは`--update`**（入れた時の版と突き合わせ、手を入れていないファイルだけ新しくし、手で直したファイルは触らずに取り込み用の差分コマンドを出す。手を入れてあってもひな型側がその間に変わっていないファイルは、1行にまとめて差分コマンドを出さない）。**微調整は入れた先で行い、ここへは戻さない**。`--dry-run`で確認だけ。**同じリポに2つ目のループを置くなら`--name <名前>`**（置き場を`.claude/loop-<名前>/`、エージェントを`<名前>-<元の名前>`にし、中身の参照とフックも付け替える。`--update`にも同じ`--name`を渡す）。入れた先の`settings.json`や工程表がgitの無視対象なら知らせ、リンタの設定（ruff・flake8・eslint・biome）があって`.claude`を外していなければ外し方を知らせる。**配置はせず**、cloneから呼ぶ。テストは`python3 -m unittest discover -s tools/tests` |
| `settings/display.json` | **正本**。表示の設定（思考の要約・focus表示）。`install.sh`が`~/.claude/settings.json`へ**無いキーだけ**足す（PCごとに変えた値は戻さない。`--no-display-settings`で省く）。中身は下の「表示の設定」 |
| `install.sh` | 上記の道具（スキル・フック・判定）を両環境へ配置。**共通ルールは入れず**、以前の版がグローバルへ入れたブロックがあれば取り除く（`--keep-global-rules`で残す）。配置後に`tools/check-limits.sh`で上限を目安チェック。`--no-codex`でCodex側の配置を省ける。**clone以外（配布先へ取り込まれた複製）から走った時は、`rules/*.md`がpull専用である旨をstderrに出す** |

`install.sh`は両方を既定で配置する。配置先は`CLAUDE_CONFIG_DIR` / `CODEX_HOME`で変更でき、再実行は冪等。
Codexをメインエージェントに使わないPCでは`./install.sh --no-codex`（または`CLAUDE_RULES_INSTALL_CODEX=0`）でCodex側の配置を丸ごと省ける。**quorumも`--no-codex` / `QUORUM_INSTALL_CODEX=0`の同じ口を持つ**。既存の配置は**自動では消さない**（残っていれば消す手順をstderrに表示する）。
**出力スタイル（`~/.claude/output-styles/`）はこのリポの配布対象ではない。**PCごとに手で置く前提。文章の書き方の決まりは出力スタイルではなく`rules/common-rules.md`の§8・§9に置き、各PJの`AGENTS.md`経由で配る——2系統に分けると片方だけ直したときに片側で再発し、出力スタイルはgit管理外で他PCへ渡らない。

CLIのインストール有無ではスキップしない。新PCへの設定の事前配布を可能にするため、Claude CodeまたはCodexが未導入でも対応する設定ディレクトリを作成する。

Codex 0.144.1の安定版hooksには、Claude Codeの`UserPromptSubmit`に相当する各ターンイベントがない。そのためCodex版は初回プロンプトだけを分類する明示的な起動ラッパーとしている。

```bash
~/.codex/hooks/codex-triage -- "調査・実装してほしい内容"
```

分類子プロセスは`--ephemeral --ignore-user-config`で起動し、再帰とセッション保存を避ける。モデルは`CODEX_TRIAGE_MODEL`、タイムアウトは`CODEX_TRIAGE_TIMEOUT`で上書きできる。分類失敗時は通常のCodex起動へフォールバックする。

独立モデルでの事前分類が不要なら、通常のCodex会話で「この依頼をトリアージしてから進めて」と自然言語で指定できる。この経路ではメインCodex自身が`$triage`で分類する。**2026-09-15以降、グローバル`AGENTS.md`はトリアージを必須発動しない**——ユーザーが言った時だけ動く。実行依頼がT1なら、Codex版`$quorum`がインストール済みの場合は提案だけで止めず、そのまま利用する。

## 表示の設定（作業中の様子を見えるようにする）

> 2026-09-25に入れた。**「何をやっているか分からない」「サブエージェントの様子が追えない」と感じたら、ここを見返す。**

### 全体に入れるもの（各PC・全PJ）

`install.sh`が次の2つを`~/.claude/settings.json`へ足す（正本は`settings/display.json`。無いキーだけ足すので、PCごとに変えた値は戻さない）。

| 設定 | 何が変わるか |
|---|---|
| `showThinkingSummaries: true` | `Ctrl+O`で、思考の中身が畳まれた印でなく要約で読める |
| `viewMode: "focus"` | 最後の依頼・ツール呼び出しの1行要約・最終応答だけを出す。全部見たい時は`/focus`で切り替えるか、このPCだけ`"verbose"`（全ツールの中身）に書き換える。フルスクリーン表示が要る（`/tui`で確かめる） |

確かめ方: `jq '{viewMode, showThinkingSummaries}' ~/.claude/settings.json`

### リポごとに入れるもの（to-doのチェックリスト）

Opus 5.5（とOpus 4.8以降・Sonnet 5以降）では、Claude Codeのto-doツールが既定で外れ、作業中のチェックリスト（`Ctrl+T`で開閉）が出ない。**全体では無効のままにし、要るリポだけで有効にする**（ツールの説明と催促がコンテキストを食うため。2026-09-25に決めた）。

- 有効にする: そのリポの`.claude/settings.json`に`{"env": {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"}}`を足す。ループのひな型を入れる時なら`tools/loop-scaffold.py … --enable-todo`で足せる
- 自分だけに効かせたい時（共有リポ）は`.claude/settings.local.json`に書く（git管理外）
- 確かめ方: `jq '.env' .claude/settings.json`（リポのルートで）。**起動時に読まれるので、足した後に始めたセッションから効く**
- 使い道: Claudeの段取りと進み具合が見える／未完了のまま「終わりました」と言われたら気づける／`--resume`で戻っても残る。セッションをまたぐ記録ではない（それは作業カードと`PROGRESS.md`）

### 設定なしで使える見方（覚えておくもの）

- サブエージェント: 入力欄の下の欄に1体1行。`/tasks`でEnterを押すとその転記を開ける。**終わった分が`/tasks`に残るのは30秒だけ**。結果は後の番に「完了の通知」としてメインへ届く
- `Ctrl+O`: 転記の詳細（各ツールの中身・モデル名・時刻）。`/goal`中は評価役の判定理由もここ
- `/recap`: ここまでの要約。3分以上離れて戻ると自動でも出る
- `/workflows`: ワークフローの工程ごとの進み具合
- 一覧の行を書き換えたい時は`subagentStatusLine`（未設定）

**他のPC**: `git pull && ./install.sh`で入る。**入れた後にClaude Codeを起動し直す**。2026-09-25の`04128f3`〜本変更の間に`install.sh`を走らせたPCは、`~/.claude/settings.json`の`env`に`CLAUDE_CODE_ENABLE_TODO_TOOLS`が残っているので手で消す。

## 他のPCへ反映する

正本の編集はこのPCだけで行い、他のPCは受け取る側に回る（「ルールを変更するとき」）。受け取る側の手順は次の4つ。**1〜2はいつでも、3は該当する時だけ、4はループのひな型を入れたリポがある時だけ**。

1. **取り込む**: `cd <claude-rulesのclone> && git pull --ff-only && ./install.sh`。`install.sh`は`~/.claude/settings.json`へ関門のフックと表示の設定を**無いものだけ**足す（告知が出る）。終わったら**Claude Codeを起動し直す**（設定と常時読み込みのルールは起動時に読まれる）
2. **確かめる**: `jq '{viewMode, showThinkingSummaries}' ~/.claude/settings.json`で表示の設定、`tools/check-record-guard.sh --repo <作業するリポ>`で関門（出たコマンドを**単独の呼び出しで**打つ）
3. **pullが止まった時**: そのPCで`IMPROVEMENTS.md`に書き足してpushしていない分があると、pullが衝突する。**正本側に同じ内容が転記済みか**を`git diff origin/main -- IMPROVEMENTS.md`で見て、転記済みなら手元の分を捨てる（`git checkout -- IMPROVEMENTS.md`）。まだ無い分だけ残してcommitし、pullし直す
4. **ループのひな型を入れたリポを上げる**（リポごと）:
   ```bash
   python3 <clone>/tools/loop-scaffold.py <リポ> --update --dry-run   # 何が起きるかを見る
   python3 <clone>/tools/loop-scaffold.py <リポ> --update
   ```
   - 手を入れていないファイルは新しくなり、手で直したファイル（多くは`pipeline.json`・`gates/<工程>.sh`・`GOAL.md`・`commands.env`）は**触らずに一覧で出る**。一覧に添えられた`git -C <clone> diff <入れた時の版> <今の版> -- …`でひな型側の変更を見て、手で取り込む
   - 実行中のループがあれば`loopctl.py finish`してから`begin`し直す（実行開始時に控える項目が増えているため）
   - 更新の後、導入先の`.claude/loop/README.md`の「導入したら最初にやること」の0（上限で止まることを先に確かめる）を1回やる
   - 入れた先のリポでcommitする（`.claude/loop/.scaffold.json`の版が新しくなる）

### 日付ごとの一回限りの手当て

- **2026-09-26**: **共通ルールをグローバルからPJへ移した**。手順は下の「2026-09-26の移行（他のPC）」。
- **2026-09-25**: この日の`04128f3`と`397b2d7`の間に`install.sh`を走らせたPCは、`~/.claude/settings.json`の`env`に`CLAUDE_CODE_ENABLE_TODO_TOOLS`が残る（to-doは全体でなくリポ単位へ変えたため）。`jq '.env' ~/.claude/settings.json`で見て、あれば消す。業務のPCでループのひな型を入れたリポは、4の`--update`で上げる（同日に不具合の修正・範囲の検査・昇格の仕組み・歯止めが入った。手で足した上限や起票の決まりは、ひな型側にも入ったので重複を見て整理する）
- **2026-09-17**: リポを作り直したので、それ以前のcloneは`git pull`が進まない。**cloneを取り直す**（消す前に`IMPROVEMENTS.md`の未pushの追記を確認）

### 2026-09-26の移行（他のPC）

このPCで行った移行（共通ルールをグローバルから各PJの`AGENTS.md`へ移し、`CLAUDE.md`を`AGENTS.md`へ統一し、`init-rules`を1枚にした）を、他のPCで行う手順。**そのPCのClaude Code（またはCodex）にこの節を読ませて進める。** 何が変わったかは`checkpoints/2026-09-26-*`にある。

**順番が大事**：PJへ共通ルールを入れる → 最後にグローバルのブロックを外す。逆にすると、入れるまでの間ルールの無いPJが出る。

1. **claude-rulesを最新にする**：`git -C <clone> pull --ff-only`。止まったら上の手順3（`IMPROVEMENTS.md`の衝突）。2026-09-17より前のcloneは取り直す。**`install.sh`はまだ実行しない**。
2. **PJの状態を見る**：`python3 <clone>/tools/embed-rules.py --scan <PJを並べた場所>`。作業ツリーが汚れているPJは先に片付けるか、今回は飛ばす（無関係な変更を混ぜない）。
3. **このPCでも作業するPJ（個人リポ）は`git pull`する**。元のPCで書き込み・統一済みなので、pullだけで`AGENTS.md`に共通ルールが入り`CLAUDE.md`が消える。手元に`CLAUDE.md`の未commitの変更があれば、pullの前に中身を見て、要る分は`AGENTS.md`のブロックの下へ移す。
4. **まだのPJ（業務・共有リポなど、元のPCに無いPJ）に書き込む**：`install-rules`スキルの「1つのPJ」の手順で1つずつ（選択肢で案内される）。
   - **読み手と個人の運用はPJごとに利用者に聞く**。業務・共有リポは、チームの運用に合わない個人の運用（自動push等）を入れない選択もある。
   - **チームで使うリポでは、全員のClaude Codeがv2.1.277以降かを利用者に確認する**。古い人がいれば`--absorb-claude-md`を付けない（`CLAUDE.md`を残し、先頭の`@AGENTS.md`で繋ぐ）。
   - **worktree必須のリポは、そのPJの決まりどおりworktreeのブランチで書き込み、PRで入れる**（mainへ直接commitしない）。
   - `--absorb-claude-md`が出した「機械で置き換えなかった行」を文脈を見て直す。`AGENTS.md`の外（PJのスクリプトのコメント、PJ固有のスキル等）に残る「グローバル§N」も`git grep`で探して直す（過去の記録は直さない）。
   - commitはPJのGit運用に従う。記録の関門は、PJの作業ではない配布の変更なので理由を述べて`CR_SKIP_RECORD_GUARD=1`で通し、pushの関門にはトレーラ`記録なし: 共通ルールの配布の変更`を付ける。
5. **最後に`./install.sh`**（`--no-codex`などの指定は前回と同じ）。`~/.claude/CLAUDE.md`・`~/.codex/AGENTS.md`から以前の共通ルールのブロックが外れ（控えは`.bak`）、Codexの`init-rules`が1枚のものに置き換わり、`install-rules`スキルが入る。**まだ書き込んでいないPJが残っているなら、外す前に利用者に確認する**（`--keep-global-rules`で残せる）。
6. **確かめる**：
   - `--scan`で対象のPJが全部「最新」
   - `~/.claude/CLAUDE.md`に`claude-rules:begin`が無い（`grep -c claude-rules:begin ~/.claude/CLAUDE.md`が0）
   - Claude Codeを起動し直し、PJで「共通ルール§5.1の見出しは？」と聞いて答えられる
   - Codexが動くPCなら、空のリポで`init-rules`を試す（元のPCではCodexがモデルのエラーで動かず未確認）
7. **気づいたズレは`IMPROVEMENTS.md`へ**（そのPCで正本は直さない）。

## PJへ共通ルールを書き込む

**入れる時はAIに頼めばよい**——Claude Code / Codexに「このPJにルールを入れて」「全PJのルールを最新にして」と言うと、`install-rules`スキルが読み手・個人の運用を選択肢で聞いてから下のコマンドを組み立てる。オプションを覚える必要は無い。

- **個人の運用はPJごとに選ぶ**：commitを指示を待たずに行う（`autocommit`）・pushを自動で行う（`autopush`）・worktreeで作業する（`worktree`）・内部ツール名を書かない（`toolname`）。選ばないと代わりの決まり（「pushはユーザーの指示があった時だけ」等）が入るか、その決まりが無くなる。選択はマーカー行に残り、更新で引き継ぐ。自分のPJは全部入り（`all`）。
- **常に入る（選べない）**：コミットの書き方・memory不使用・AI署名なし・外に出す文面でMarkdownを使わない・応答の書き方。

```bash
python3 <claude-rules>/tools/embed-rules.py --list-options                     # 選べる個人の運用
python3 <claude-rules>/tools/embed-rules.py <PJ> --options all --absorb-claude-md   # 初回（選択は必須。none / all も可）
python3 <claude-rules>/tools/embed-rules.py <PJ> --target claude --options none # Claudeだけの相手
python3 <claude-rules>/tools/embed-rules.py <PJ>                  # 2回目以降: 前回の選択と書き込み先のまま最新へ
python3 <claude-rules>/tools/embed-rules.py --scan ~/Develop      # 配下のPJの状態（最新・古い・未書き込み・CLAUDE.mdが残っている）
python3 <claude-rules>/tools/embed-rules.py <PJ> --dry-run         # 変わるファイルだけ出す
python3 <claude-rules>/tools/embed-rules.py <PJ> --check           # 書き込んだ版が最新か（古ければ exit 1）
python3 <claude-rules>/tools/embed-rules.py <PJ> --remove          # 書き込んだものを取り除く
```

| --target | 書き込む先 | 読まれ方 |
|---|---|---|
| `both`（既定） | `AGENTS.md`の先頭。`--absorb-claude-md`で`CLAUDE.md`の中身をブロックの下へ移し`CLAUDE.md`を消す（付けなければ`CLAUDE.md`の先頭に`@AGENTS.md`を足して繋ぐだけ） | どちらも`AGENTS.md`を直接読む（Claude Codeはv2.1.277以降） |
| `claude` | `CLAUDE.md`の先頭 | Claudeだけ |
| `codex` | `AGENTS.md`の先頭 | Codexだけ |

- 共通ルールはマーカー（`claude-rules:embed:begin` / `end`）で囲み、マーカー行に版（正本のcommit）と種類と選択を刻む。**更新は同じコマンドをもう一度**——マーカー間だけを差し替え、外に書いたPJ固有の指示には触らない。PJ固有の指示はブロックの下へ書く。
- `--absorb-claude-md`は、グローバル時代の決まった言い回し（「グローバル`~/.claude/CLAUDE.md`に従う」「グローバル§5の差分」等）を「共通ルール」を指す語へ置き換え、機械で判断できない行（`CLAUDE.md`・グローバルという語が残る行）を行番号付きで出す。そこはAIが文脈を見て直す。
- PJに`CLAUDE.md`があるとClaude Codeは`AGENTS.md`を読まない（`NOTES.md`「配布の仕組み」）。統一しないまま残す時は`@AGENTS.md`の行が要る。
- 本文は相手のホームにある物を指さない。上限の判定は`<PJ>/.claude-rules/check-limits.sh`（道具が一緒に置く）を指し、マーカー間を14,336B、外をPJの上限（6,144B）で分けて測る。
- このPCに以前のグローバルの共通ルールが残っていると二重に読まれる。道具と`check-limits.sh`が知らせ、`install.sh`で外れる。
- commitはしない。

## ルールを変更するとき

**編集するPCはここ（claude-rulesのcloneを持つPC）に限る。** 他PCで気づいた改善は、そのPCの改善メモ（`IMPROVEMENTS.md`等）に書き足すところまでにして、**正本の編集はこのPCで行う**。PJの`AGENTS.md`の共通ルールのブロックを直接編集しないのと同じ理由で、正本を複数のPCから触ると版が分岐する。

**改善メモ（`IMPROVEMENTS.md`）はどのPCから書いてよい。** 正本はリポrootの`IMPROVEMENTS.md`（git管理）で、`install.sh`がClaude / Codex両方の配置先からsymlinkを張る（`~/.claude/skills/init-rules/IMPROVEMENTS.md`）。**リポを移動したら再installする**——symlinkは絶対パスを焼き込むので、移動すると全PCのリンクが同時に切れ、追記が正本へ届かないまま黙って落ちる（`install.sh`は張り直し前にリンク切れを警告し、張り直し後に解決を検証する）。

配布先へ**取り込まれた複製**（他リポの`bundled/`配下など）で`install.sh`を走らせると、`rules/*.md`がpull専用である旨をstderrに出す（`rules/`に未コミットの変更があればさらに強く警告する）。止めはしないので、出たら編集をやめて改善メモへ回す。

1.**このリポの`rules/common-rules.md`（またはスキル）を編集する**。PJの`AGENTS.md`のブロック内は直接編集しない（次の書き込みで消える）
2. `python3 -m unittest discover -s tools/tests`（版ごとの中身と上限を見る）
3. commit / push
4. PJへ反映する：`python3 tools/embed-rules.py --scan ~/Develop`で「古い」PJを出し、それぞれ`python3 tools/embed-rules.py <PJ>`（前回の選択のまま）。PJごとにcommit / push。AIに「全PJのルールを最新にして」と頼めば同じことをする
5. 他のPCでは`git pull && ./install.sh`（道具）と、各PJの`git pull`（共通ルール）

## 経緯

> ※ 2026-09-17に**履歴を1コミットへ畳んだ**ので、以下に出てくるこのリポのコミットハッシュ（`956bf8b`など）は、いまのリポでは解決できない。当時の識別子として残してある。他リポのハッシュ（quorum・cadence）はそのまま有効。

- 2026-06-17: グローバル`~/.claude/CLAUDE.md`と`/init-rules`を作成（当初は版管理外）
- 2026-07-10: Hermes Agent調査の応用でルール3点を追加（常時ロード数値上限／スキル化の前向き自問／スキルdiff承認・使用後自己改善）したのを機に、本リポへ切り出して配布可能化
- 2026-08-19: **外部へpushできないPC（subtreeのpull-only mirror）から届いた改善メモ3件を反映**し、双方向の同期経路を整備した。
  - **ルール本体**（`956bf8b`）: §5.1のworktreeの終い方に元cloneの`git pull --ff-only`を追加（Claude / Codex両方）／§2の上限を`14KB`表記から`14,336B`へ改めPROGRESS.mdに総バイト12,288Bを追加／§4・§7を圧縮。差し引き −770BでグローバルCLAUDE.mdは14,238B → 13,468B。**見出し番号は据え置いた**——`§5.1`は各PJの`CLAUDE.md`から参照されており、詰めると他PCの参照が黙って壊れる。
  - **上限判定の一本化**（`f6395d6` / `b60ba39`）: `tools/check-limits.sh`を新設し、install時のグローバル2ファイルだけだった検査を**PJのCLAUDE.md 6,144BとPROGRESS.md（行数・総バイト）まで**広げた。上限は`CR_LIMIT_*`かPJの`.claude/limits.env`で上書きできる（§2の「PJのCLAUDE.mdで上書き可」の機械可読版）。
  - **Codex配置の任意化**（`f6395d6` / `8d5d4ff`）: `--no-codex` / `CLAUDE_RULES_INSTALL_CODEX=0`を追加。`AGENTS.md`は3リポとも注入するため、cadenceにも同じ口を入れた（cadence `ec06314`。quorumは実装済みだった）。スキップは「配置しない」であって「消す」ではないので、残置物は自動削除せず消す手順を案内する（quorumの判断に合わせた）。
  - **状態採取**（`f716e6f`）: `tools/collect-state.sh`を新設。pushできないPCで実行して出力を貼るだけで、正本のハッシュ・正本と生成物のドリフトdiff・ブロック構成・配置物が1回で分かる。subtree配下でも動き、`$HOME`は伏せ、`settings.json`は登録件数しか出さない。
  - この往復で判明したこと: そのPCのリポ本体は13ファイル全ハッシュ一致で、**ズレていたのは生成物だけ**（install未実行）。懸案だった約50Bの差は手当ての実測 +87Bで説明でき、**quorum / cadenceのブロックは3,206Bで完全一致＝版ズレ無し**だった。
- 2026-08-29: 別PCの改善メモ4件を反映。**§2の上限超過の対処からツール名を落とし、動作で書いた**（`/cadence optimize-context`を名指ししていたため、cadenceを入れていないPCでは指す先の無い手順が常時ロードのルールに残っていた。`tools/check-limits.sh`の超過メッセージも同様に直した）。**§9「応答の書き方」を新設**し、「応答のたびに、いま何をやっているかを1行で置く」をClaude / Codex両方へ入れた（従来は別PCの生成物側だけに入れていたためinstallで消える状態だった。条件を「長い作業では」から外し、形も`いま進めているサブタスク = …`からサブタスクに限らない形へ広げた）。あわせて **正本を編集するPCを1台に限る旨を「ルールを変更するとき」に明記**した（改善メモの「直せるものはその場で直す」を、どのPCからでも正本を触ってよいと読める余地があった）。2026-08-15の残件だった「正本の所在をマーカー行の近くに書く」は、マーカー行が既に`変更はリポのrules/global-rules.mdへ`を持っており充足済みだった。
- 2026-08-29: **`IMPROVEMENTS.md`を新設**（`install.sh`が`skills/init-rules/`からsymlink）。配布先PCから「上流にIMPROVEMENTSが無い」と指摘されたため。quorum / cadenceは同方式を持つがclaude-rulesだけ無く、改善ネタが配布先のローカル文書に溜まり、**会話でのコピペでしか上流へ渡らなかった**（反映済みか生きている候補かも配布先から見えない）。受領済みの6件を反映印つきで収録した。symlinkはcadenceで実発生したdangling事故（IMPROVEMENTS 2026-08-27）に合わせ、**張り直し前のstale/dangling警告と張り直し後の解決検証**を入れてある。
- 2026-08-29: **cadenceの利用をやめたことに全体を追随させ**（`d125adb`）、**`init-rules`の雛形から個人アカウント名を落とした**（同）。cadence側は`CLAUDE.md`（上限の内訳を2ブロックへ）／README（ブロック図・install順・`--no-codex`の説明）／§5.2の例外リスト／Codex共通ルール／`hooks/triage-rubric.txt`と分類フック2本／`skills/codex-triage/SKILL.md`の7ファイル。**トリアージ分類はT0 / T1 / T2aの3値**になった。**過去の経緯は事実なので書き換えず、これからの手順を書いている箇所だけを直した。**個人アカウント名は、このスキルが業務PCへも配布されるため落とし、`gh api user --jq .login` / `gh org list`で候補を出してユーザーに確認する形にした（ownerは雛形が決め打ちしてよい値ではない）。
- 2026-08-29: **§9に「番号や記号を、それが何を指すか書かずに出さない」を追加**（配布先の履歴から本文を受け取った分）。独立節にせず既存の「応答の書き方」へ入れた——本文の最後が「着手や完了を伝えるときも同じ」で逐一報告の決まりを直接受けており、離すと片方だけ読まれるため。**あわせて環境からcadenceを撤去**（各PCの`cadence-triage`ブロック・スキル・コマンド。quorum側に残っていた`CADENCE`分類の1行も正本で直した）。グローバルCLAUDE.mdは14,039 → 13,017 → 14,040Bで、**撤去で空いた分がそのまま追記に充てられた**。
- 2026-08-31: **§3「タスク実行中」に「PJ側が『必須』と定めた関門のサブエージェント（レビュー役・検査役）は、都度の許可を取らず呼ぶ」を追加**（`bdba73d`。Claude / Codex両方）。業務のモノレポで、PJの`CLAUDE.md`が必須と書いている関門でも、セッション側の「求められない限りサブエージェントを呼ばない」が勝って毎回確認で止まっていた。ユーザーが一度許可しても**セッションが変わると再発する**ため、恒久の決まりとしてグローバルへ置いた。**改善メモの案はトリアージ節への追記だったが§3に変えた**——トリアージ節はquorumが注入するブロックで、quorum未導入のPCには存在せず、そこに書くと2026-08-27のcadenceと同じ「指す先の無い手順」になる。同じ理由でfableの例外（監査ログが要る側）は書いていない。置き場のバイトは§2の「過去の経緯が必要になった時だけ該当日を遡る」（§1の表と重複）と§6のrecall行（同節2行目と重複）を畳んで作り、グローバルCLAUDE.mdは14,040 → 14,186B（**残り150B**）。
- 2026-09-02: 別PCの改善メモ1件（2026-09-01）を反映。**§9に「英数字と日本語の間に半角スペースを入れない」を追加**（Claude / Codex両方。応答・手元のMDやスライド・外部へ出す文面の**書く面すべて**に効かせた）。同じ学びはPJ側に2026-07-08から載っていたが、スコープが外部へ出す文面に限られていたため2か月効かず、スライド2本で810箇所出ていた。**置き場のバイトは、§9の記号ルールの例をコードブロックから本文へ畳み、言い換え5か所を削り、`rules/*.md`自身を新ルールに合わせて作った**（境界の半角スペースがglobal-rules.mdに190か所）。グローバルCLAUDE.mdは14,186 → 14,167Bで、**ルールを1本増やして残量が19B増えた**。**ルールを載せている文書自身が190か所その規則を破っていた**ことが、効かなかったもう一つの理由でもある。あわせて**`check-limits.sh`に残量表示と`△`**（残りが既定512B / 5行を切った時。割合ではなく残量にしたのは、グローバルが上限まで使い切る設計で98%前後を常時走るため割合警告が信号にならないから）、**`install.sh`にclone以外の複製から走った時の警告**（`rules/*.md`はpull専用。実際に配布先の複製で正本を編集してinstallまで通した事故があったため）を入れた。**出力スタイル（`~/.claude/output-styles/`）は配布対象に含めない**と決め、READMEに明記した——文章の決まりが出力スタイルとグローバルの2系統に分かれること自体が今回の再発の原因で、`rules/*.md`の§8・§9へ一本化する。
- 2026-09-12: **checkpointの置き場と粒度を変えた**。`docs/checkpoints/YYYY-MM-DD.md`（1日1ファイル・同日は同ファイルに追記）から、**リポ直下の`checkpoints/YYYY-MM-DD-作業内容.md`（作業のまとまりごとに1ファイル・作業内容は日本語）**へ。同じ日に無関係な作業を複数走らせると1ファイルが長くなりすぎ、過去を遡る時に読む量が問題になっていた。ファイル名に作業内容が出るので、開かずに当たりを付けられる。`docs/`を挟むのもやめた（1階層浅くなり、`PROGRESS.md`からのリンクも短い）。直したのは`rules/global-rules.md` §1の表・§2、`rules/codex-global-rules.md`の同2箇所と完了時の1行、`skills/init-rules/SKILL.md`と`skills/codex-init-rules/SKILL.md`の雛形。**`docs/adr/`は据え置き**（ADRはcheckpointと別の軸で、置き場を変える理由が無い）。**既存PJの`docs/checkpoints/`は自動では動かさない**——過去のリンクが切れるため、移すかどうかは各PJで決める（新規分から新しい置き場に書けば混在しても読める）。置き場のバイトは§1の表の役割欄と§2の重複（「作業のまとまりごとの詳細ログ」）を畳んで作り、グローバルCLAUDE.mdは14,167 → 14,263B（**残り73B**）。
- 2026-09-12: **`REQUIREMENTS.md`と`PROGRESS.md`の書き分けを「決めたこと／進み具合」の軸で切り直した**。従来`REQUIREMENTS.md`は「何を作るか・仕様/スコープ・未決事項」で、**決めた方針・作業・予定の置き場が明示されていなかった**ため、それらが`PROGRESS.md`の「次にやること」に流れ込み、計画の本体が進捗側に溜まっていた（`PROGRESS.md`は60行・12,288Bの上限があり、溜まると真っ先に溢れる）。§1の表の役割欄を`REQUIREMENTS.md` = 決めたこと（要求・方針・作業・予定）・スコープ・未決事項、`PROGRESS.md` = いまの状態（現在地・進行中・次の一手・ブロッカー）・ADRに改め、**§4に「決めたことは`REQUIREMENTS.md`、進み具合は`PROGRESS.md`。計画の本体を二重に持たない」を置いた**（§4は元々「§1の表で分ける」しか言っておらず、いちばん迷う2ファイルの境目を名指ししていなかった）。`init-rules`の雛形も追随し、`REQUIREMENTS.md`に「要求・方針」「やること / バックログ（予定を含む）」を新設、`PROGRESS.md`の見出しを「次にやること」から「次の一手」へ変えて出所を注記した。Codex側も同内容。置き場のバイトは、§1の`notes/`注記をCodex版と同じ短い言い回しへ、§2の「checkpointはセッション開始時に読まない」を§1の表の「いつ読む」列と重複のため削除、§3の`REQUIREMENTS.md`更新義務2行を1行に、§2の完了欄とADRの2文を圧縮して捻出し、グローバルCLAUDE.mdは14,263 → 14,281B（**残り55B**）。**ADRを`PROGRESS.md`に置く扱いは据え置いた**——新しい軸では「決めたこと」側に見えるが、ADRは判断の理由であり`docs/adr/`への切り出し口も既にある。動かすなら別途決める。
- 2026-09-12: **`REQUIREMENTS.md`とADRを「生きている分だけ」にした**。片付いた要求・方針・予定・決定はその場で消し、経緯はcheckpoint側に預ける。置いたのは§3「タスク完了時」の3行目（`NOTES.md` / `REQUIREMENTS.md`の更新と同じ行に「**片付いた要求・方針・予定とADRは消す**（経緯はcheckpointにある）」）——**同じ節の1行目が「詳細な作業ログをその作業のcheckpointに書く」なので、手順の順序そのものが「消す前に経緯が残っている」を保証する**。§1の表の役割欄にも`REQUIREMENTS.md` / `PROGRESS.md`の両方に「**生きている分だけ**」を入れ、`REQUIREMENTS.md`の「いつ書く」を「片付いた時」まで広げた。`PROGRESS.md`の「**常にスリムに保つ**」はこの語に置き換えた（スリムに保つのは結果で、手段は片付いた分を消すこと）。`init-rules`の雛形も追随（`REQUIREMENTS.md`の注記とバックログ欄、`PROGRESS.md`のADR欄に「片付いたら消す」）。Codex側も同内容。**`NOTES.md`は対象外**——恒常的に効く学びを残す場所で、片付くという概念が無い。置き場のバイトは§2の導入文の前置き（「長期PJでは」）と、上限の箇条書きで英日2回言っていた`"cut bytes, not meaning"`の和訳を畳んで捻出し、グローバルCLAUDE.mdは14,281 → 14,310B（**残り26B**。次に1行足す前に畳む場所が要る）。あわせて§3完了時の「次にやること」を表と揃えて「次の一手」へ直した。
- 2026-09-12: **`NOTES.md`の片付け方を3つの出口で定義した**。従来の§6は「肥大化してきたらcheckpoint方式に逃がす」の1行だけで、**そもそも`NOTES.md`に入れるべきでなかった一回限りのログを追い出す面しか見ていなかった**。しかも生きている学びをcheckpointへ移すと、checkpointは「過去の経緯を調べる時だけ読む」場所なので二度と読まれない。`REQUIREMENTS.md`と違い`NOTES.md`の項目には「完了」が無いため、**消してよい条件を3つに限った**：①ルール・スキル・テストに昇格した（二重管理になるので移した先を1行残して本体を消す。このリポ自体がその経路で、配布先の気づきが`rules/global-rules.md`の§9になっている）②前提が変わって効かなくなった ③一回限りのログだった（checkpointへ）。**引き金は定期棚卸しにせず、§1の表の「いつ読む」（似たトピックを扱う前）に乗せた**——開いた項目だけをその場で見直すので費用がほぼゼロで、実際に参照される項目から鮮度が保たれる。**項目ごとの取得日は`init-rules`の雛形にだけ入れ、グローバルのルール本文には書いていない**（②の判定材料だが、生成される`NOTES.md`の冒頭に書けば足り、常時ロードのバイトを使う価値が無い）。置き場のバイトは§1の表の`NOTES.md`欄の「・運用上の知見」（§6の2つ目と重複）、§7冒頭の「グローバルは共通骨格だけ。」（見出しと§1冒頭で既出）、§6のmemory行の言い換えと`notes/insights.md`の例示を畳んで捻出し、**差し引き −14BでグローバルCLAUDE.mdは14,310 → 14,296B（残り40B）**。ルールを1本厚くして残量が増えた。
- 2026-09-12: **共通ルール全体を一度圧縮した**（残り40Bでは次の1ルールが入らないため）。**ルールの数は減らさず、見出し番号も据え置き**、削ったのは他所で既に言っている語・言い換え・前置きだけ：§1冒頭の「新PJの立ち上げは`/init-rules`」を§7へ畳む／§2の副題と導入文（表の役割欄と同じ内容）／§5の「共通原則：」ラベルと§7の「§5.1・§5.2は共通に定義済み」（§5冒頭と重複）／§6 memory行の「新しく書かず」（「使わない」に含む）／§9の理由の言い直し（「防ぐのは記録ではなく毎回の1行」「記号だけを置いて済ませない」は直前の文が既に言っている）／各所の「〜する」「〜を行う」の語尾・「悪い例／良い例」ラベル・二重の例示。`"cut bytes, not meaning"`は和訳だけにした。`rules/global-rules.md`は12,112 → 9,928B（−2,184B）、グローバルCLAUDE.mdは14,296 → 12,112Bで**残り2,224B**。削った59行を1行ずつ見直し、**意味が薄れる3箇所は戻した**——上限判定の「PJルートで」（実行場所で見るPJが変わる）、§4の「原則」（例外を閉じすぎる）、表の「終了時」（タスク終了と読める。「セッション終了時」に）。Codex側は残量3,795Bで圧縮していない。新ファイル自身が§9の半角スペース規則を破っていないことも機械で確認した（検出3件は見出し番号と、§8・§9の「使わない記法」「悪い例」の引用そのもの）。
