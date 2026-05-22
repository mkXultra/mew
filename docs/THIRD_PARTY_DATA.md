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

### Redistribution Status

`private_only` is the conservative default. It permits local-only audit,
conversion dry runs, and in-memory validation, but generated fixture commits
remain disallowed.

`commit_allowed` means a reviewer has selected the status and the source
manifest must include notice, citation, and provenance fields: source dataset,
source host, declared license, and license source as non-placeholder values;
absolute non-placeholder source and license-source URLs; immutable revision;
raw file hashes in full `sha256:<64 hex>` form; citation targets when
required; `generated_fixture_commit_policy: no_vendor_by_default`; and this
notice file with complete coverage flags.

`blocked` means neither committed generated fixtures nor local generated fixture
packs should proceed from that source manifest until the status changes.

### Current Repository Gate

For `mteb/MemBench`, Phase C fixture commits require a source audit report from
`python -m mew.memory_eval.membench validate-source-manifest <source_manifest.json> --require-commit-allowed`
whose `phase_c_commit_preconditions.status` is `commit_allowed_ready`.

This gate does not permit raw-source vendoring. It only permits a later reviewed
MemBench-derived fixture pack when the source manifest, notices, citations, and
hash provenance are complete.
