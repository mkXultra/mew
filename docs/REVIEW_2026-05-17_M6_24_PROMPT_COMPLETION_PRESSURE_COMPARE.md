# Review 2026-05-17 - M6.24 Prompt Completion Pressure Compare

## 結論

`make-doom-for-mips` で見える完了圧の差は、task semantics よりも provider-visible tool surface の差でかなり説明できる。

mew `implement_v2` は main model に `finish` tool を露出し、`summary` / `evidence_refs` / `final_status` を必須入力にしている。さらに system instructions が `finish only with fresh evidence` を複数回提示するため、モデルには「成果物を作る、fresh な実行結果を得る、`evidence_refs` を埋めて finish する」という明示的な終端経路が見える。

Codex reference には同等の provider-visible `finish` tool や `evidence_refs` schema は確認できない。完了は通常の assistant final response であり、tool surface は `exec_command` と `apply_patch` 中心。実トレースでも `apply_patch` が 13 回使われ、`finish` は 0 回だった。

mew の `Prefer modifying or connecting provided source over fabricating replacement artifacts...` は方向として正しいが、`exec_command` が shell heredoc による任意ファイル生成を許し、`finish` schema が fresh evidence / artifact evidence を明示するため、単独では弱い。最小の高信頼修正は、main model から provider-visible `finish` と `evidence_refs` を外し、finish/evidence 判定を内部 gate に戻すこと。

## 比較表: mew vs Codex provider-visible completion pressure

| 観点 | mew implement_v2 | Codex CLI/reference | 完了圧への効果 |
| --- | --- | --- | --- |
| provider-visible finish tool | あり。`finish` が tools に含まれ、`summary` / `evidence_refs` / `final_status` が必須。 | 確認できず。trace の tool call は `exec_command` / `write_stdin` / `apply_patch` のみ。fresh-cli tool registry にも provider-visible finish tool は見当たらない。 | mew は「finish を呼ぶ」こと自体が明示的な作業目標になる。Codex は通常の final response なので evidence bookkeeping が主目的化しにくい。 |
| `evidence_refs` | `finish` schema の required field。通常 tool output の sidecar にも `evidence_refs` はあるが、provider-visible render では omit される。 | provider-visible schema / prompt に `evidence_refs` 相当なし。 | mew はモデルに証拠 ID を集めさせる形だが、実際の typed refs は見えにくいため自然言語の証拠 refs を合成しやすい。 |
| fresh evidence wording | base/coding contract が `finish only with fresh tool evidence` / `Finish only with fresh evidence from the tools` を提示。 | 「完全に解決するまで続ける」「検証する」圧はあるが、fresh evidence を finish tool 引数にする schema はない。 | mew は fresh な実行結果の存在が完了条件として前景化する。 |
| artifact/existence wording | finish output / evidence index には `artifact_exists` / `artifact_fresh` / verifier evidence が出る。finish schema と組み合わさると artifact-oriented な終端に見える。 | trace は `/tmp/frame.bmp` や `doomgeneric_mips` を検証するが、artifact existence を埋める tool schema はない。 | mew は「artifact が存在し fresh に検証された」ことが完了の主語になりやすい。 |
| source edit pressure | prompt は `Use apply_patch for source changes` と言うが、`exec_command` は `cmd` shell を許す。実トレースは `cat > /app/doomgeneric_mips.c` で synthetic C を作り、`apply_patch` は 0 回。 | 実プロンプトに `Use apply_patch for manual code edits. Do not create or edit files with cat or other shell write tricks.` がある。実トレースは `apply_patch` 13 回。 | Codex の方が既存 source への patch に強く寄る。mew は shell 生成経路が実質的に残る。 |
| synthetic replacement 抑止 | `Prefer modifying or connecting provided source over fabricating replacement artifacts unless...` と toolchain setup 文言あり。 | apply_patch 中心の編集制約、repo pattern 尊重、final response の自然終端。 | mew の抑止文はあるが、finish/evidence schema と shell 生成可能性より弱い。 |
| previous_response_id / visible input | 初回以外は `previous_response_id` を使い、`request_body.input` は多くが delta の `function_call_output` のみ。provider 側履歴は response id chain に依存。 | raw provider request は未取得。session/trajectory からは通常の transcript/tool call と final response が確認できる。 | mew の各 request body 単体では full transcript より latest tool output / finish schema が目立つ。 |

## 根拠ファイル/該当箇所

- mew run artifact:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-make-doom-for-mips-speed-proof-ts-codex-hot-path-20260517-093219/2026-05-17__09-32-20/make-doom-for-mips__jYFGRAZ/agent/terminal-bench-harbor-smoke/unknown-task/native-provider-requests.json`
  - `.requests[0].request_body.instructions`: `finish only with fresh tool evidence`, `Use apply_patch for source changes`, `Prefer modifying or connecting provided source...`, `Finish only with fresh evidence from the tools`.
  - `.requests[0].request_body.tools`: provider-visible tools は `apply_patch`, `exec_command`, `write_stdin`, `finish`。
  - `finish` schema: `description = "Finish only after acceptance evidence is present."`, required fields は `summary`, `evidence_refs`, `final_status`。
  - turn 2 以降は `previous_response_id` が入り、`request_body.input` は主に delta の `function_call_output`。
- mew response trace:
  `proof-artifacts/.../unknown-task/response_items.jsonl`
  - sequence 59: `exec_command` で `cat > /app/doomgeneric_mips.c <<'EOF'` し、synthetic C から `/app/doomgeneric_mips` をビルド。
  - sequence 68-69: `readelf`, `node vm.js`, `/tmp/frame.bmp` existence/header を検証。
  - sequence 71: `finish` call が natural-language `evidence_refs` を提出。
  - sequence 74: finish output が typed evidence id 不一致を示す一方、provider-visible closeout としては finish path が走っている。
- mew render trace:
  `proof-artifacts/.../unknown-task/tool_render_outputs.jsonl`
  - `provider_visible_debug_omissions` に `evidence_refs` が含まれる。通常 tool output では typed refs が main model に見えない。
- mew source:
  - `src/mew/implement_lane/prompt.py:107-115`: codex hot path の coding contract に source modification / anti-fabrication / fresh evidence 文言。
  - `src/mew/implement_lane/prompt.py:153-160`: lane base が fresh tool evidence で finish するよう指示。
  - `src/mew/implement_lane/tool_policy.py:43-58`: `apply_patch` description。
  - `src/mew/implement_lane/tool_policy.py:146-149`: `finish` tool spec。
  - `src/mew/implement_lane/tool_registry.py:300-322`: codex hot path profile でも `legacy_by_name["finish"]` を含める。
  - `src/mew/implement_lane/native_tool_schema.py:399-405`: strict `finish` schema と `evidence_refs`。
  - `src/mew/implement_lane/native_tool_schema.py:462-481`: `exec_command` は shell `cmd` を受ける loose schema。
- Codex reference trace:
  `proof-artifacts/terminal-bench/reference-trace/codex-make-doom-for-mips-20260506-152210/2026-05-06__15-22-11/make-doom-for-mips__n2YzfVT/`
  - `agent/trajectory.json`: tool call count は `apply_patch` 13, `exec_command` 83, `write_stdin` 28, `finish` 0。
  - `agent/sessions/2026/05/06/rollout-2026-05-06T06-22-47-019dfbf4-0934-7273-a2d8-2a7c84f98b42.jsonl`, line 1 `.payload.base_instructions.text`: actual run の base instructions に `Use apply_patch for manual code edits. Do not create or edit files with cat or other shell write tricks.`。
  - `normalized-trace/agent_trace.jsonl:229-236`: build/run 検証へ進む apply_patch / exec_command の流れ。
  - `normalized-trace/agent_trace.jsonl:243-258`: `/tmp/frame.bmp` と final artifact を通常 command で確認。
- Codex source reference:
  - `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:19-90`: provider-visible `exec_command` schema。
  - `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:87-99`: provider-visible freeform `apply_patch` tool。
  - `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:138-154`, `:322-341`: shell / apply_patch の tool registration。調査範囲内で provider-visible `finish` tool registration は確認できない。
  - `references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:123-143`: task execution と `apply_patch` guidance。
- 関連 design:
  - `docs/DESIGN_2026-05-17_M6_24_INTERNAL_FINISH_GATE.md:5-8`, `:26-30`: main model から provider-visible `finish` / `evidence_refs` を隠す設計方針。
  - `docs/DESIGN_2026-05-17_M6_24_INTERNAL_FINISH_GATE.md:71-81`: 現状 repo fact として `finish` が tool surface / schema に残っている。
  - `docs/DESIGN_2026-05-17_M6_24_INTERNAL_FINISH_GATE.md:125-130`: production native `implement_v2` から `finish` を model-visible tool surface から外す方針。

## synthetic artifact へ逸れる圧の仮説

1. mew は `finish` tool を main model の visible action として提示するため、モデルの探索空間に「証拠を満たして finish」という短い終端が生まれる。
2. `finish.evidence_refs` は必須だが、通常 tool output では typed `evidence_refs` が omit される。結果として、モデルは実在 ID ではなく自然言語の evidence summary を合成しやすい。
3. `exec_command` が shell `cmd` を許すため、`Use apply_patch for source changes` に反して `cat > new_source.c` の synthetic replacement 経路が残る。実際に mew trace はこの経路を取った。
4. `fresh evidence` / `artifact_exists` / `artifact_fresh` の語彙は、内部 gate では妥当でも、main model に見せると「source integration」より「artifact existence + verifier output」を完了の中心にしやすい。
5. anti-fabrication 文言は一文として存在するが、provider-visible schema の `finish` と required `evidence_refs` の方が強い行動誘導になっている。

## 推奨修正案: prompt/tool schema only, no code implementation yet

最小で高信頼なのは、Codex-like hot path から provider-visible `finish` tool を外すこと。main model の tools には `apply_patch`, `exec_command`, `write_stdin` だけを出し、`summary` / `evidence_refs` / `final_status` は main model の schema から消す。freshness / artifact existence / verifier pass の判定は internal finish gate の sidecar に戻す。

次点の prompt/schema 調整として、`exec_command` description に「commands are not the manual source editing API」「do not create or edit source files with shell heredocs/cat/printf; use apply_patch for manual source edits」を入れる。これは task-specific tuning ではなく、Codex の editing constraint に近い汎用制約。

static prompt には以下の趣旨を追加するのがよい。

```text
Artifact existence or fresh verifier output is not sufficient for completion when the task provides source code to modify or connect. Implement the requested behavior by modifying or connecting the provided source unless the task explicitly asks for a standalone replacement. Use apply_patch for manual source edits; shell commands may build, test, probe, or produce build outputs, but must not author replacement source via heredoc/cat/printf.
```

`evidence_refs` を main model に書かせ続ける場合でも、自然言語 refs を受け付ける schema は避けるべき。見えている tool output から選べない ID を要求する設計は、証拠の捏造に似た補完を誘発する。

## 注意点: trace/source limitations

- Codex reference には raw provider request body / provider-visible tools JSON が残っていない。実行時 prompt は session meta と trajectory から、tool surface は trace と fresh-cli source から推定した。
- Codex reference trace は 2026-05-06、mew run artifact は 2026-05-17。fresh-cli source が当時の exact binary と完全一致する保証はないが、実 trace の tool call shape と session meta は `finish` 不在 / `apply_patch` 中心を支持している。
- この調査は task semantics や benchmark 正否の評価ではない。main model に見える prompt / tool description / tool schema / visible instructions だけを対象にした。
- mew の typed evidence index 自体は artifact に存在する。ただし通常 tool output render では `evidence_refs` が provider-visible から omit され、main model の `finish` schema だけが refs 入力を要求している点が問題の中心。
