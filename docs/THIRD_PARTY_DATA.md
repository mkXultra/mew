# Third-Party Data Notices

This document records source-audit metadata for third-party datasets that may
be used to generate local evaluation artifacts. It is not legal advice. Treat
declared upstream license and citation fields as audit inputs that still need
review before committing derived data.

## Hugging Face `mteb/MemBench`

| Field | Value |
| --- | --- |
| Source dataset | `mteb/MemBench` |
| Source host | Hugging Face |
| Source URL | <https://huggingface.co/datasets/mteb/MemBench> |
| Pinned revision | Required in each source manifest as `source_revision`; use `source_revision_status: pinned` only for immutable revisions. |
| Declared license | The Hugging Face dataset card declared `mit` during the 2026-05-23 source-audit check. |
| License source | Hugging Face dataset card for `mteb/MemBench`. |
| Citation required | Yes, when MemBench-derived data or evaluation artifacts are used. |
| Citation targets | The dataset card asks users to cite the dataset and MTEB; it also lists LMEB/MMTEB-related processing citations where indicated by the card. |
| Local-cache/no-vendor policy | Raw MemBench source data must stay in a local cache or external source checkout; do not commit raw MemBench data to this repository. |
| Generated fixture commit policy | No generated MemBench-derived fixture pack may be committed unless the source manifest validates as `commit_allowed_ready`. |
| Redistribution status options | `private_only`, `commit_allowed`, `blocked`. |

### Local Hugging Face Export

MemBench MTEB-style Hugging Face configs may be prepared into the local source
shape expected by the converter with:

```sh
python -m mew.memory_eval.membench prepare-hf-mteb-qrels /path/to/local/membench-source \
  --dataset mteb/MemBench \
  --subset single_hop \
  --revision <40-character dataset commit sha>
```

The command loads configs named `<subset>-corpus`, `<subset>-queries`, and
`<subset>-qrels`; `--include-top-ranked` also loads
`<subset>-top_ranked`. It writes only local raw-source files
`corpus.jsonl`, `queries.jsonl`, `qrels.jsonl`, optional
`top_ranked.jsonl`, and `source_manifest.json` in the chosen output
directory. The output directory must not be under `fixtures/memory_eval`.

This export path uses the Python `datasets` package from the development
dependency group. Runtime installs do not need `datasets`; if it is unavailable,
the command fails with a clear message instead of downloading anything through a
hidden fallback. The default loader requests local-files-only cache access; a
cache miss should fail rather than download MemBench during preparation. Older
`datasets` versions that cannot provide `DownloadConfig(local_files_only=True)`
should fail clearly instead of silently falling back to network access.

`--revision` is required and must be an immutable-looking pinned commit SHA.
The generated source manifest remains conservative: `local_cache_only: true`,
`generated_fixture_commit_policy: no_vendor_by_default`, and
`redistribution_status: private_only` unless explicitly overridden. Preparing
local raw source files and a source manifest does not imply permission to
commit raw data or generated fixtures.

For local profile runs, use the profile wrapper instead of the lower-level
commands. The smoke profile is the smallest wiring check:

```sh
python -m mew.memory_eval.membench profile membench-smoke200-typed
```

The intermediate sample profile runs more queries against a larger sampled
corpus before a future full profile:

```sh
python -m mew.memory_eval.membench profile membench-sample1000-typed
```

Profiles perform local source preparation, source-manifest validation, sampled
dry-run conversion, and TypedCards validation. They use the pinned Hugging Face
`mteb/MemBench` dataset commit
`1dd519e4d91573e2818d850eb4405fb290663ac2` by default so repeated profile runs
use the same upstream source snapshot. They still write only local artifacts
under `tmp/membench-profiles` by default and do not permit raw-source or
generated-fixture commits.

### Redistribution Status

`private_only` is the conservative default. It permits local-only audit,
conversion dry runs, and in-memory validation, but generated fixture commits
remain disallowed.

`commit_allowed` means a reviewer has selected the status and the source
manifest must include notice, citation, provenance, and explicit reviewer
approval fields: source dataset, source host, declared license, and license
source as non-placeholder values; absolute non-placeholder source and
license-source URLs; immutable revision; raw file hashes in full
`sha256:<64 hex>` form; citation targets when required;
`generated_fixture_commit_policy: no_vendor_by_default`; this notice file with
complete coverage flags; and a `redistribution_review` block.

The required `redistribution_review` block is:

```json
{
  "approved": true,
  "reviewer": "reviewer name or handle",
  "reviewed_at": "calendar-valid YYYY-MM-DD",
  "decision_basis": "short non-placeholder basis for the decision",
  "scope": "generated_fixtures_only"
}
```

This approval scope never permits raw MemBench source vendoring. It only
records that a reviewer approved generated fixture commit readiness based on
the manifest, notices, citations, and source provenance. It is still not legal
advice.

`blocked` means neither committed generated fixtures nor local generated fixture
packs should proceed from that source manifest until the status changes.

### Current Repository Gate

For `mteb/MemBench`, Phase C fixture commits require a source audit report from
`python -m mew.memory_eval.membench validate-source-manifest <source_manifest.json> --require-commit-allowed`
whose `phase_c_commit_preconditions.status` is `commit_allowed_ready`.

This gate does not permit raw-source vendoring. It only permits a later reviewed
MemBench-derived fixture pack when the source manifest, notices, citations, and
hash provenance are complete and `redistribution_review.approved` is exactly
`true` for `scope: generated_fixtures_only`.
