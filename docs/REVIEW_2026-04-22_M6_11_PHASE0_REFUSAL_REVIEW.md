# Review: M6.11 Phase 0 Refusal Separation

## No findings

Reviewed the uncommitted changes in [src/mew/errors.py](/Users/mk/dev/personal-pj/mew/src/mew/errors.py:1), [src/mew/codex_api.py](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:61), [src/mew/agent.py](/Users/mk/dev/personal-pj/mew/src/mew/agent.py:359), [tests/test_codex_api.py](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:83), and [tests/test_runtime.py](/Users/mk/dev/personal-pj/mew/tests/test_runtime.py:2507).

The refusal/error split is internally consistent:

- [src/mew/errors.py:9](/Users/mk/dev/personal-pj/mew/src/mew/errors.py:9) and [src/mew/errors.py:17](/Users/mk/dev/personal-pj/mew/src/mew/errors.py:17) make refusals a distinct subtype while still preserving `ModelBackendError` compatibility.
- [src/mew/codex_api.py:87](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:87), [src/mew/codex_api.py:120](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:120), and [src/mew/codex_api.py:300](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:300) separate refusal extraction from assistant-text extraction for both JSON and SSE responses, and [src/mew/codex_api.py:312](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:312) raises `CodexRefusalError` before the generic empty-text failure path.
- [src/mew/agent.py:359](/Users/mk/dev/personal-pj/mew/src/mew/agent.py:359) and [src/mew/agent.py:414](/Users/mk/dev/personal-pj/mew/src/mew/agent.py:414) stop retrying refusal errors without changing retry behavior for the existing transient parse/timeout markers.
- [tests/test_codex_api.py:101](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:101), [tests/test_codex_api.py:182](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:182), [tests/test_codex_api.py:202](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:202), and [tests/test_runtime.py:2538](/Users/mk/dev/personal-pj/mew/tests/test_runtime.py:2538) cover the main intended boundary: refusal is no longer treated as assistant text, `call_codex_json()` preserves refusal instead of collapsing it into a parse failure, and `think_phase()` does not retry a refusal.

Validation run:

- `PYTHONPATH=src python3 -m unittest tests.test_codex_api tests.test_runtime` passed.

## Residual risks / test gaps

- No end-to-end test currently exercises the non-stream JSON refusal branch in [src/mew/codex_api.py:304](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:304) through [src/mew/codex_api.py:313](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:313). Current refusal coverage in [tests/test_codex_api.py:182](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:182) through [tests/test_codex_api.py:219](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:219) is stream-only.
- No end-to-end stream test covers the `completed_response` fallback path in [src/mew/codex_api.py:144](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:144) through [src/mew/codex_api.py:152](/Users/mk/dev/personal-pj/mew/src/mew/codex_api.py:152). The helper coverage in [tests/test_codex_api.py:116](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:116) through [tests/test_codex_api.py:132](/Users/mk/dev/personal-pj/mew/tests/test_codex_api.py:132) shows the extractor works on payloads, but not that the full SSE path surfaces a refusal when no refusal delta events arrive.
