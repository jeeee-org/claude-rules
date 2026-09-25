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
| `.claude/loop/judge/judgments.jsonl` | 判断役の全判定と人の正解（**git管理する**。学習の材料） |
| `.claude/loop/judge/calibration.json`・`lessons.md` | 較正で決まった閾値と、判断役に見せる誤りの例 |
| `.claude/loop/judge/rules.json` | 判断役から出たルールの候補と採否（影で検証中・採用中・廃止） |
| `.claude/loop/bin/rules.py` | ルールの検査4種（loopctlから使う） |
| `.claude/loop/state.json` | 実行中の状態（git管理外） |
| `.claude/loop/stats/gates.jsonl` | ゲートの検査ごとの合否の記録（git管理する。打率と外す候補の材料） |
| `.claude/loop/candidates.md` | ループの中で気づいた別件・改善の種。**ループは起票しない**ので、ここに溜まる。起票するかは人が決める |

## 導入したら最初にやること

0. **上限で止まることを先に確かめる**（打ち切りの経路は、普段の実行では発火しない）: `pipeline.json`の`limits.max_shards`を1にして`begin`し、同じ工程へ2回`start`して止まることを見る。確かめたら値を戻す

1. `.claude/loop/GOAL.md`に完了条件を書く
2. `.claude/loop/gates/commands.env`にビルド・リント・テストのコマンドを書く（空のままのゲートは不合格になる）
3. `.claude/loop/pipeline.json`の工程を、このリポの作業に合わせる（汎用版は`instructions`・`outputs`・`review_focus`を書き換える）
4. ゲートを空打ちして、形が通るかを見る: `LOOP_STEP=<工程> LOOP_DIR=.claude/loop REPO_ROOT=. bash .claude/loop/gates/<工程>.sh`
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

途中で様子を見る:

- `python3 .claude/loop/bin/loopctl.py status` — 工程ごとの状態・差し戻し回数・分担・止まっている理由
- `/tasks` — 動いているサブエージェント。Enterでその転記を開ける（完了後30秒まで）
- `Ctrl+O` — 転記の詳細表示（各ツール呼び出しの中身）
- `Ctrl+T` — Claudeのto-doチェックリスト。Opus 5.5では既定で出ないので、要るなら`.claude/settings.json`の`env`に`"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"`を足す（導入時なら`--enable-todo`）

## 人の出番

- 人待ちをまとめて見る: `loopctl.py pending`。工程役の問い（問い・選択肢・推奨・判断役の答え）と、判断役が人へ回した判断（推奨はpass|fail）と、理由だけの停止が並ぶ
- まとめて答える: `loopctl.py answer <工程>=<選択肢> <工程>=<選択肢> ... --note "<理由>"`。推奨どおりなら`<工程>=推奨`、名指ししていない分を全部推奨どおりにするなら`--recommended`。**どれを選んだかは`judgments.jsonl`に残り**、判断役の学習の材料になる（`calibrate --apply`で`lessons.md`の「人の裁定」に載る）
- 1工程ずつなら従来どおり`loopctl.py decide <工程> pass|fail --note "<理由>"`。外部待ちが解けたら`loopctl.py unblock <工程>`
- 実行全体の上限で止まった: 時間なら`loopctl.py resume --extend <秒>`（予算を延ばして再開。延ばさずに`resume`するとすぐまた止まる）。ほかの上限は`pipeline.json`の`limits`を見直し、`accept-self`してから`resume`
- 自動で通った判断が誤っていた: `loopctl.py override <判断id> <正しい答え> --note "<理由>"`（判断idは`judge/judgments.jsonl`）
- 人が付き添って対話で回す時: `loopctl.py pause`（Stopフックの催促が止まる。工程役の報告の形は引き続き確かめる）
- 実行を閉じる: `loopctl.py finish`（以後は工程役の報告の形も確かめない）

## 判断役を育てる（較正）

判断役は、答えに確信度を添えて返す。loopctlは確信度が閾値以上の答えだけを自動で採り、それ以外は人へ回す。人の答え（`decide`・`answer`・`override`）は正解として`judgments.jsonl`に溜まる。

工程役が人に聞く問い（`block --ask`）も同じ仕組みに乗る。統括役は止める前に判断役へ問いを渡し、その答えと確信度を`block`に添える。人の答えが溜まって問いの型（`--qid`、既定は`ask:<工程の型>`）ごとに閾値が出れば、以後は閾値に届いた判断役の答えで止めずに進む（抜き取りは同じく`audit_rate`）。

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
  "items": [],
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
- 項目の一覧は`begin --items-file <一覧>`（1行1件、またはJSONの配列）か`--items a b c`。実行中に足すのは`loopctl.py add-item <id> ...`。一覧は実行の状態に持つので、`pipeline.json`（ループ自身）を書き換えずに済む。上限は`limits.max_items`
- 全項目が済んでから動く共通の工程は、`"after": ["*/fix"]`のように書く
- 判断役の問いのidは項目をまたいで同じなので、較正と誤りの例は項目の間で共有される。ルールの候補も、パスの項目idを`{item}`に戻して型の単位で育つ
- 工程役とゲートは、展開後の定義を`loopctl.py show <工程>`で読む（ゲートには`LOOP_ITEM`・`LOOP_OUTPUTS`も渡る）

## 必ず止まる場面（must_stop）

統括役は、`pipeline.json`の`must_stop`に挙がった操作の直前で必ず止まる。既定は共有ブランチへのpush・PRのマージ・デプロイと本番への反映・外へのメッセージの送信・データの削除。記録のpushが既定の手順のリポなどでは、ここから外す（取り消せない操作は、この一覧にかかわらず人に確かめる）。

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
| `limits.max_shards` | 30 | 実行全体で着手した分担の数の上限 |
| `limits.max_items` | 100 | 項目ごとに回す時の項目の数の上限（`begin`と`add-item`で確かめる） |
| `sunset_min_runs` | 10 | 一度も落ちない検査を外す候補に挙げるまでの実行回数 |
| `judge.max_promoted_per_step` | 3 | 工程あたりの採用中のルールの上限 |
| `judge.default_threshold` | 0.9 | 較正前に使う閾値 |
| `judge.promote_min_fires` | 5 | ルールの候補を昇格させるのに要る、正しい検出の回数（誤検出は0回が条件） |
