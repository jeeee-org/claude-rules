# ループ（claude-rulesのひな型から導入）

このリポのループ系エージェント一式。導入元は[claude-rules](https://github.com/jeeee-org/claude-rules)の`tools/loop-scaffold.py`。**ここから先の微調整はこのリポの中で行う**（導入元へは戻さない）。

## 構成

| パス | 役割 |
|---|---|
| `.claude/agents/loop-conductor.md` | 統括役。工程を振り、状態をloopctlで動かす。**公式の早止まり対策の常駐指示**を末尾に持つ |
| `.claude/agents/<工程役>.md` / `review-*.md`・`step-*.md` | 工程役とレビュー役（サブエージェント）。報告の形（`STATUS:`行）が決まっている |
| `.claude/agents/gate-judge.md` | 判断役。選択肢の問いに答えと確信度を返す |
| `.claude/loop/pipeline.json` | 工程の並び・担当・ゲート・判断役の問い・上限値 |
| `.claude/loop/GOAL.md` | 完了条件 |
| `.claude/loop/GATES.md` | 何を決定論に置くかの考え方 |
| `.claude/loop/gates/` | 決定論ゲート（`<工程>.sh`）・共通部品（`lib.sh`）・回すコマンド（`commands.env`） |
| `.claude/loop/bin/loopctl.py` | 状態を動かす唯一の道具（遷移・順序・ゲート実行・判断の記録と較正） |
| `.claude/loop/bin/stop-guard.py` | Stopフック。未完了があるのに文章だけで止まったら、残りを名指しして続けさせる（上限あり） |
| `.claude/loop/bin/subagent-report-guard.py` | SubagentStopフック。工程役が決まった形の報告なしに終わるのを1回差し戻す |
| `.claude/loop/bin/shared-tree-guard.py` | PreToolUseフック（Bash）。実行中、工程役・レビュー役が共有の作業ツリーで`git checkout`・`stash`・`reset`・`restore`・`clean`・`switch`するのを止める（未コミットの変更が工程の成果物なので。`git worktree add`した外の場所では通す） |
| `loopctl.py scratch` | 壊して試す・前と比べるための写しを、共有の作業ツリーの外に毎回新しい場所で作り、パスを出す（既定は未コミットの変更ごと、`--head`でコミット済みの版だけ）。作れなければ失敗で終わるので、工程役・レビュー役は`d=$(python3 .claude/loop/bin/loopctl.py scratch) \|\| exit 1`で使い、壊す処理へ進まない。消すのは`scratch --remove <パス>`。守りのフックはgitの巻き戻ししか止めず、ファイルの直接の書き換えは止められないので、写しの作り方をここで揃える |
| `.claude/loop/judge/judgments.jsonl` | 判断役の全判定と人の正解（**git管理する**。学習の材料） |
| `.claude/loop/judge/calibration.json`・`lessons.md` | 較正で決まった閾値と、判断役に見せる誤りの例 |
| `.claude/loop/judge/rules.json` | 判断役から出たルールの候補と採否（影で検証中・採用中・廃止） |
| `.claude/loop/bin/rules.py` | ルールの検査4種（loopctlから使う） |
| `.claude/loop/state.json` | 実行中の状態（git管理外） |
| `.claude/loop/tmp/<工程>/<分担>/` | 工程役ごとの一時置き場（git管理外）。`start`が作って工程役へ渡し、`begin`が前の実行の分を消す。並列の工程役が共有の`/tmp`で別の問いの実測を拾わないため |
| `.claude/loop/stats/gates.jsonl` | ゲートの検査ごとの合否の記録（git管理する。打率と外す候補の材料） |
| `.claude/loop/candidates.md` | ループの中で気づいた別件・改善の種。**ループは起票しない**ので、ここに溜まる。起票するかは人が決める。作業の別件と、ループの仕組みそのものの課題（`[ひな型]`）の2節に分け、実行の終わりに`loopctl.py retro`の振り返りを貼る |

## 導入したら最初にやること

0. **上限で止まることを先に確かめる**（打ち切りの経路は、普段の実行では発火しない）: `loopctl.py begin --limit max_shards=0`（項目ごとに回すなら`--allow-empty`も）で始め、同じ工程へ2回`start`して止まることを見て、`loopctl.py finish`で閉じる。上限の差し替えはこの実行の間だけで、`pipeline.json`は書き換えない。閉じた実行に「作業中」の工程が残るが、次の`begin`で消える

1. `.claude/loop/GOAL.md`に完了条件を書く
2. `.claude/loop/gates/commands.env`にビルド・リント・テストのコマンドを書く（空のままのゲートは不合格になる）
3. `.claude/loop/pipeline.json`の工程を、このリポの作業に合わせる（汎用版は`instructions`・`outputs`・`review_focus`を書き換える）。`outputs`の名前を`report`・`summary`・`findings`・`analysis`で始まる`.md`にしない（Claude Codeがサブエージェントの`Write`を止める。`begin`が知らせる）
4. ゲートを空打ちして、形が通るかを見る: `LOOP_STEP=<工程> LOOP_DIR=.claude/loop REPO_ROOT=. bash .claude/loop/gates/<工程>.sh`
   - リンタがあるリポでは、ひな型のPython（`.claude/`）をリンタの対象から外す（ひな型はリポのリンタ設定に合わせて書いていない。例: ruffなら`extend-exclude = [".claude"]`）。導入の道具が設定を見つけたら知らせる
   - 工程役が提出前に同じ条件でゲートを試すには`loopctl.py gate <工程> --dry-run`（状態も記録も変えない）。人がゲートを直している時もこれで確かめられる
   - コミットまでをループで回すなら、汎用版の`commit`工程（`gates/commit.sh`）を使い、pushまでを1作業とするPJは`commands.env`の`PUSH_REQUIRED=1`
5. 判断役（`.claude/agents/gate-judge.md`）の`model`を選ぶ。既定のhaikuは形や網羅の問い向き。問いが文書の読み込み（過去の裁定・仕様との突き合わせ）を要するなら、sonnetへ上げる
6. `.claude/settings.json`がgitの無視対象なら（導入の道具が知らせる）、フックはこのworktreeにしか無い。**ループはこのworktreeから起動し、終わってもworktreeを消さない**

## 回し方

```bash
claude --agent loop-conductor            # 統括役をメインセッションとして起動
# 人が見ていない実行にするなら、許可の確認を減らす（auto mode）と組み合わせる
```

ひな型を入れた直後の変更は、回す前にcommitしておく（実装のゲートが「実行を始めた時点からの差分」で範囲を見るため。未コミットのまま始めると、その時点のファイルは検査から外れる）。

**`--agent`で起動する。** 普通のセッションで「回して」と頼んでも統括役の手順では回るが、Stopフックの早止まり対策は統括役として起動したセッションにしか効かないので、区切りごとに止まって人の返事を待つ。

統括役への最初の一言は「GOAL.mdのとおりにループを回して」でよい。`/goal`（別モデルが毎番、完了条件を確かめる）と併用してもよい: `/goal .claude/loop/bin/loopctl.py status で全工程が完了と出る`。

**統括役が落ちたら**（端末ごと閉じた・セッションが切れた）: 状態はファイル（`state.json`）にあるので、同じ場所で`claude --agent loop-conductor`を起動し直せば、`loopctl.py status`から続きに入る。走っていたサブエージェントの工程は「作業中」のまま残るので、統括役がその工程役を振り直す（やり直し）。**作業ツリーの未コミットの変更はその工程の途中の成果物なので、消さない**（`git checkout`・`stash`で片付けない）。

途中で様子を見る:

- `python3 .claude/loop/bin/loopctl.py status` — 工程ごとの状態・差し戻し回数・分担・止まっている理由
- `/tasks` — 動いているサブエージェント。Enterでその転記を開ける（完了後30秒まで）
- `Ctrl+O` — 転記の詳細表示（各ツール呼び出しの中身）
- `Ctrl+T` — Claudeのto-doチェックリスト。Opus 5.5では既定で出ないので、要るなら`.claude/settings.json`の`env`に`"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"`を足す（導入時なら`--enable-todo`）

## 人の出番

- `begin`が「枝の工程」を知らせたら: 前提を2つ以上待つ集約の工程があるのに、後ろのどの工程も前提にしていない工程がある。その結果は集約に入らないので、入れるなら集約の工程の`after`に足す
- 人待ちをまとめて見る: `loopctl.py pending`。工程役の問い（問い・背景・選択肢・推奨・判断役の答え）と、判断役が人へ回した判断（推奨はpass|fail。それぞれ選ぶと何が起きるか）と、理由だけの停止が並ぶ。1工程に問いが複数あれば`<工程>#<番号>`で1つずつ並ぶ
- まとめて答える: `loopctl.py answer <工程>=<選択肢> <工程>#2=<選択肢> ... --note "<理由>"`。答えは問いと答えの文言のまま返るので、成果物へはそれを写す（言い換えない）。推奨どおりなら`<工程>=推奨`、名指ししていない分を全部推奨どおりにするなら`--recommended`。**どれを選んだかは`judgments.jsonl`に残り**、判断役の学習の材料になる（`calibrate --apply`で`lessons.md`の「人の裁定」に載る）
- 1工程ずつなら従来どおり`loopctl.py decide <工程> pass|fail --note "<理由>"`。外部待ちが解けたら`loopctl.py unblock <工程>`
- 実行全体の上限で止まった: 時間なら`loopctl.py resume --extend <秒>`（予算を延ばして再開。延ばさずに`resume`するとすぐまた止まる）。ほかの上限は`pipeline.json`の`limits`を見直し、`accept-self`してから`resume`
- 自動で通った判断が誤っていた: `loopctl.py override <判断id> <正しい答え> --note "<理由>"`（判断idは`judge/judgments.jsonl`）
- 人が付き添って対話で回す時: `loopctl.py pause`（Stopフックの催促が止まる。工程役の報告の形は引き続き確かめる）
- 実行を閉じる: `loopctl.py finish`（以後は工程役の報告の形も確かめない）。全工程が完了すると統括役が閉じる（閉じずに止まろうとするとStopフックが促し、促しても閉じなければ`max_auto_continues`回目の後にフックが閉じる）。閉じた実行に残った人待ちは`status`・`pending`に「閉じた実行の残り」と出て、次の`begin`で消える

## 判断役を育てる（較正）

判断役は、答えに確信度を添えて返す。loopctlは確信度が閾値以上の答えだけを自動で採り、それ以外は人へ回す。人の答え（`decide`・`answer`・`override`）は正解として`judgments.jsonl`に溜まる。**閾値は較正で問いごとに決まり、較正の前は判断役の答えを自動で採らない**（`judge.default_threshold`が既定のnull）。判断役は確信度を高めに言いがちなので、人の答えが無いうちに任せると、人を素通りして学習の材料も溜まらない。

| 段階 | 起きること | 人がすること |
|---|---|---|
| 育てる（最初） | 判断役の答えはすべて人へ回る（確信度つきで`pending`に並ぶ）。人の答えと理由が正解として溜まる | `answer`で答え、**理由を`--note`で書く**（`lessons.md`の「人の裁定」になり、判断役が次から読む）。人の答えがいつも推奨どおりなら、問いの置き方を見直す（下） |
| 任せる | 較正で閾値が出た問いだけ、閾値に届いた答えを自動で採る。`audit_rate`の分は抜き取りで人へ | `calibrate`で問いごとの一致率を見て、任せてよければ`calibrate --apply`（**任せる範囲を広げるのは人**） |
| 決定論へ上げる | 判断役の不合格の理由が決まった形なら、ルールの候補として影で走る | 条件を満たしたルールを`promote`（下の節。**上げるのも人**） |

**育てる段階に置く問いは、人の答えが割れうるもの（仕様の解釈・簡略化してよいか）だけにする。** レビュー役がすでに見ている観点を判断役にも重ねると、人の答えは推奨の追認になり、全部同じ答えなので学習の材料にもならない（個人の開発PJの実測: 最初の5項目で15件すべて人へ回り、人の答えは15件すべて推奨どおり。利用者は6項目目から判断役の問いを外し、レビュー役・決定論ゲート・最後の結合テストに任せた）。`calibrate`は、人の答えが直近`judge.agree_streak`（既定10）件続けて判断役と同じ問いに「問いを外すか任せる段階へ」の目安を出す。

判断役が選択肢の外の答え（`yes/no`の問いに`pass`など）や無回答を返したら、loopctlは人へ回す前に1回だけ判断役へ選び直させる（`judge`が理由を出して断るので、統括役がそれを判断役へ渡す）。2回目も外なら人へ回し、その工程には推奨を出さない（推奨を失敗側に倒すと、`answer --recommended`が中身を見ない差し戻しになる）。

工程役が人に聞く問い（`block --ask`）も同じ仕組みに乗る。統括役は止める前に判断役へ問いを渡し、その答えと確信度を`block`に添える。1工程に問いを複数並べられる（`block --ask`を重ねる。上書きしない）。人が選ぶための背景は`--context`に書く（元の問い・決めた答え方の要点・どれを選ぶと何が起きるか・迷った点）。人の答えが溜まって問いの型（`--qid`、既定は`ask:<工程の型>`）ごとに閾値が出れば、以後は閾値に届いた判断役の答えで止めずに進む（抜き取りは同じく`audit_rate`）。

```bash
python3 .claude/loop/bin/loopctl.py calibrate          # 問いごとの正答率と、出せる閾値を見る
python3 .claude/loop/bin/loopctl.py calibrate --apply  # 閾値と誤りの例を反映する
```

- 閾値は「確信度t以上の標本で正答率が目標（既定95%）以上、かつ標本が下限（既定20件）以上」になる最小のt。出せない問いは人へ回し続ける。
- 自動で通した判断のうち`audit_rate`（既定10%）は抜き取りで人へ回る。自動化が進んでも正解が溜まり続けるように。
- 誤りの例は`lessons.md`に書かれ、判断役が毎回読む。モデルの重みは学習しない（手元でできる範囲の強化）。
- 閾値は判断役のモデルごとに決まる。`gate-judge.md`の`model`を替えたら`calibration.json`を消して取り直す。

## 判断役の結論を決定論へ昇格させる

判断役は、機械的な理由（節が無い・idが抜けている等）で不合格を出す時に、同じことを確かめる検査を「ルールの候補」として添える。候補はすぐには使わず、以後の判断で**影で**走らせて、判断役・人の結論と合うかを記録する（合否には使わない）。

```bash
python3 .claude/loop/bin/loopctl.py rules              # 候補と実績（検出回数・正しい/誤り・見逃し）
python3 .claude/loop/bin/loopctl.py promote <ルールid>  # 採用（人が承認）。以後その工程の決定論ゲートで効く
python3 .claude/loop/bin/loopctl.py retire <ルールid>   # 廃止
```

- ルールは「検査に落ちたら不合格」の検出器だけ。検査はファイルの有無・パターンの有無・禁止パターン・idの網羅の4種の組み合わせだけ（判断役に自由なコードを書かせない）。
- 昇格の条件は、正しい検出が`judge.promote_min_fires`（既定5）回以上で、誤検出が0回。条件を満たさないルールの`promote`は拒む（承知の上なら`--force`）。
- 実績は`judgments.jsonl`から毎回数え直す。後から`override`で正解を直すと、実績も変わる。
- 候補と採否は`judge/rules.json`（git管理する）。

## 検査を減らす（打率と外す候補）

```bash
python3 .claude/loop/bin/loopctl.py gate-stats   # 検査ごとの実行回数・不合格回数と、外す候補
```

- ゲートの各行の末尾の〔…〕が検査の鍵。鍵ごとに1回のゲートで1件記録する。
- `sunset_min_runs`（既定10）回以上走って一度も落ちていない検査を「外す候補」に挙げる。自動では外さない（当たりゼロには、上流で捕れている・見えていない・抑止が効いている、の3通りがある）。
- 昇格したルールは工程あたり`judge.max_promoted_per_step`（既定3）本まで。足すなら1本見直す。

## 項目ごとに回す（per_item）

1件ずつ独立に「決める → 測る → 直す → 記録」のように回すときは、`pipeline.json`に工程の型を書く。`begin`で項目ごとに展開され、工程は`<項目>/<工程>`のidになる。1件が人待ちで止まっても、ほかの項目は進む。

```json
"per_item": {
  "items_file": ".claude/loop/items.txt",
  "serial": false,
  "after": ["triage"],
  "steps": [
    {"id": "decide", "worker": "step-worker", "reviewer": "step-reviewer", "gate": "gates/outputs.sh",
     "instructions": "{item} について決める", "outputs": ["loop-out/{item}/decide.md"], "judge_questions": []},
    {"id": "fix", "worker": "step-worker", "reviewer": "step-reviewer", "gate": "gates/outputs.sh",
     "instructions": "{item} の決定どおりに直す", "outputs": ["loop-out/{item}/fix.md"], "judge_questions": []}
  ]
}
```

- 型の中の`{item}`は項目idに置き換わる。項目の中では直前の型の工程が前提になる。最初の工程の前提は`after`（共通の工程）
- 項目の一覧は`per_item.items_file`（リポのルートからのパス。1行1件、またはJSONの配列）に書いておけば`begin`が読む。その場で渡すなら`begin --items-file <一覧>`か`--items a b c`（こちらが優先）。**0件では始まらない**（渡し忘れを防ぐ。後から`add-item`するつもりなら`--allow-empty`）。実行中に足すのは`loopctl.py add-item <id> ...`。一覧の中身は実行の状態に持つので、`pipeline.json`（ループ自身）を書き換えずに済む。上限は`limits.max_items`
- **`"serial": true`で一覧の順に1件ずつ**回す。各項目の最初の工程が前の項目の最後の工程を前提にするので、`next`は次の1件だけを返し、`start`も順番を守らせる。同じ場所を触る項目（作業ツリーを共有する実装など）は並列にしない。前の項目が止まれば後ろは待つ
- **`serial`では、人待ちになりうる工程を型の最後に置かない。** 判断役の問いを持つ工程や人に聞く工程は、`"after": ["run"]`のように前提を明示した枝にし、型の最後は記録（commit・push）などの人を待たない工程にする。最後に置くと、較正前は判断役の問いが全部人へ回るので、夜の実行が1件目で止まる（業務のテストPJの実例）。枝の工程は後ろの項目の前提にならないので、人の答えを待つ間も列は進む
- 全項目が済んでから動く共通の工程は、`"after": ["*/fix"]`のように書く
- 判断役の問いのidは項目をまたいで同じなので、較正と誤りの例は項目の間で共有される。ルールの候補も、パスの項目idを`{item}`に戻して型の単位で育つ
- 工程役とゲートは、展開後の定義を`loopctl.py show <工程>`で読む（ゲートには`LOOP_ITEM`・`LOOP_OUTPUTS`も渡る）

## 着手前の確かめ（precheck）

測る・外へ繋ぐ工程は、前提（クラウドのログインの残り時間・トンネル・VPN）が切れていると、工程役が作業を書き終えてから気づいて人待ちになる。工程に`"precheck": "gates/<名前>.sh"`を書くと、`loopctl.py start`が着手の前にそれを回し、**exitが0以外なら工程を止めて（人待ち）工程役を起こさせない**。理由は✖の行（無ければ最後の行）。人が前提を直して`unblock`すれば着手できる。ゲートと同じく`REPO_ROOT`・`LOOP_STEP`・`LOOP_ITEM`が渡る。既定の時間切れは120秒（`precheck_timeout`）。

```bash
# 例: gates/precheck-aws.sh — ログインの残りが工程の見込み（ここでは60分）より短ければ止める
. "$LOOP_DIR/gates/lib.sh"
need_cmd "AWSのログイン" "aws sts get-caller-identity --profile $AWS_PROFILE >/dev/null"
# 残り時間を見るならSSOのキャッシュ（~/.aws/sso/cache/*.json の expiresAt）と比べる検査を足す
gate_end
```

## 必ず止まる場面（must_stop）

統括役は、`pipeline.json`の`must_stop`に挙がった操作の直前で必ず止まる。既定は共有ブランチへのpush・PRのマージ・デプロイと本番への反映・外へのメッセージの送信・データの削除。記録のpushが既定の手順のリポなどでは、ここから外す（取り消せない操作は、この一覧にかかわらず人に確かめる）。

## 振り返り（retro）

`loopctl.py retro`で、実行の数字をまとめて出す: 経過と完了した工程・項目ごとの経過（本線＝型の最後の工程が終わるまでと、枝の人待ちを含む全体を分けて出す。工程が止まっていた時間＝人待ち・人の指示で止めた時間は除いた数を先に出す）と差し戻し・差し戻しの理由の分布（レビュー／決定論ゲート／判断役／人、ゲートは検査の鍵ごと）・Stopフックの催促の回数・人待ちの件数と種類・判断役が自動で決めて人が後から正した件数。統括役は止まる前にこれを`candidates.md`の「振り返り」節へ貼る（`--json`もある）。決定論ゲートの誤判定は機械では数えられないので、気づいたら`[ひな型]`で1行残す。

## 同じリポに2つ目のループを置く

claude-rulesの`tools/loop-scaffold.py <リポ> --profile generic --name <名前>`で入れる。置き場は`.claude/loop-<名前>/`、エージェントは`<名前>-loop-conductor`などになり、中身の参照とフックの登録も付け替わる。起動は`claude --agent <名前>-loop-conductor`。更新するときは`--update --name <名前>`。

## ループ自身を改修しない

実行を始めた時点で、ループ自身のファイル（`.claude/loop/bin/`・`gates/`・`pipeline.json`・`.claude/agents/`・`.claude/settings.json`）のハッシュを控え、ゲートのたびに突き合わせる。変わっていれば`loop-self`の検査で不合格。人が意図して直したなら`loopctl.py accept-self`で控え直す。

## 上限値（pipeline.json）

| キー | 既定 | 意味 |
|---|---|---|
| `max_auto_continues` | 3 | 状態が進まないままStopフックが続行させる回数。超えたら実行を止める（公式: 2〜3回） |
| `max_rework` | 3 | 1工程の差し戻しの上限。超えたら工程を止めて人へ |
| `time_budget_sec` | null | 経過時間の予算。入れると催促に`elapsed Xs / Ys`を添える（公式: 時間の目安があると早く終わる。拘束力は無い） |
| `limits.time_budget_hard` | false | trueなら`time_budget_sec`を打ち切りにする（超えたら次の着手とStopフックで実行を止める） |
| `limits.max_total_rework` | 10 | **実行全体**の差し戻しの合計の上限（`max_rework`は1工程あたり） |
| `limits.max_shards` | 30 | 実行全体で、**工程ごとの最初の着手を除いた**分担の数（分担の追加・差し戻し後の着手し直し）の上限。暴走の歯止めで、工程の数そのものは数えない（問いごとに40工程を回す実行が1工程1分担でも止まったため。2026-09-28） |
| `limits.max_items` | 100 | 項目ごとに回す時の項目の数の上限（`begin`と`add-item`で確かめる） |
| `sunset_min_runs` | 10 | 一度も落ちない検査を外す候補に挙げるまでの実行回数 |
| `judge.max_promoted_per_step` | 3 | 工程あたりの採用中のルールの上限 |
| `judge.default_threshold` | null | 較正前に使う閾値。null＝較正で閾値が出た問いだけ任せ、それまでは全部人へ（育てる段階から始める）。最初から任せたいリポだけ数値（例0.9）を書く |
| `judge.agree_streak` | 10 | 人の答えがこの件数続けて判断役と同じ問いに、`calibrate`が「問いを外すか任せる段階へ」の目安を出す |
| `judge.promote_min_fires` | 5 | ルールの候補を昇格させるのに要る、正しい検出の回数（誤検出は0回が条件） |

どの上限も、`begin --limit <名前>=<値>`でその実行の間だけ差し替えられる（`pipeline.json`は書き換えない。`status`に差し替えた値が出る）。
