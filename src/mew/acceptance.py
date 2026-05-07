from __future__ import annotations

import re
import shlex

from .acceptance_evidence import (
    long_dependency_artifact_proven_by_call,
    tool_call_evidence_ref,
    tool_call_terminal_success,
)
from .long_build_substrate import (
    command_evidence_to_tool_call,
    long_dependency_artifact_proven_by_command_evidence,
)
from .tasks import clip_output


ACCEPTANCE_CONSTRAINT_KEYWORDS = (
    "acceptance",
    "allowed",
    "avoid",
    "compile",
    "create",
    "do not",
    "don't",
    "ensure",
    "exact",
    "expected",
    "forbid",
    "must",
    "no ",
    "not ",
    "only",
    "output",
    "pass",
    "preserve",
    "produce",
    "replace",
    "save",
    "should",
    "specified",
    "verify",
    "warning",
    "without",
)

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOOL_ID_RE = re.compile(r"\btool(?:\s+call)?\s*#?\s*(\d+)\b", re.IGNORECASE)
_RUNTIME_TMP_ARTIFACT_RE = re.compile(r"(/tmp/[A-Za-z0-9._/@%+=:,\-]+)")
_ABSOLUTE_PATH_RE = re.compile(r"(/[A-Za-z0-9._/@%+=:,\-]+(?:/[A-Za-z0-9._/@%+=:,\-]+)*)")

_WRITE_TOOLS = {"write_file", "edit_file", "edit_file_hunks"}
_GROUNDING_TOOLS = {
    "git_diff",
    "git_status",
    "glob",
    "read_image",
    "read_images",
    "read_file",
    "run_command",
    "run_tests",
    "search_text",
}

_RUNTIME_FRESH_RUN_MARKERS = (
    "emulator",
    "execute",
    "fresh run",
    "interpreter",
    "node ",
    "run ",
    "vm",
)
_RUNTIME_ARTIFACT_GENERATION_MARKERS = (
    "frame",
    "frames",
    "generated",
    "screenshot",
    "stdout",
    "will be written",
    "will write",
    "writes",
    "written",
)
_RUNTIME_ARTIFACT_CREATED_MARKERS = (
    "and /tmp/",
    "artifact ok",
    "bmp ok:",
    "bmp_header_ok=true",
    "created /tmp/",
    "exists=true",
    "frame_bytes",
    "frame ok",
    "magic=bm",
    "path=/tmp/",
    "saved /tmp/",
    "saved first frame",
    "saved frame",
    "exists size=",
    "written to /tmp/",
)
_RUNTIME_ARTIFACT_EXPECTED_PATH_MARKERS = (
    "frames will be saved to /tmp/",
    "output will be saved to /tmp/",
    "saved to /tmp/",
    "will save to /tmp/",
    "will write /tmp/",
    "will write to /tmp/",
)
_RUNTIME_ARTIFACT_CLEANUP_MARKERS = (
    "cleaned",
    "cleanup",
    "deleted",
    "remove",
    "removed",
    "rm -f",
    "unlink",
)
_RUNTIME_VISUAL_ARTIFACT_MARKERS = (
    "frame",
    "frames",
    "framebuffer",
    "image",
    "render",
    "rendered",
    "screenshot",
    "screen size",
)
_RUNTIME_VISUAL_ARTIFACT_QUALITY_TASK_MARKERS = (
    "appropriate",
    "appropriately",
    "check that",
    "correct",
    "correctly",
    "expected",
    "reference",
    "similar",
    "verify",
    "will check",
)
_RUNTIME_VISUAL_ARTIFACT_QUALITY_EVIDENCE_MARKERS = (
    "expected dimensions",
    "expected resolution",
    "frame_quality_ok",
    "reference similarity",
    "similarity passed",
    "ssim passed",
)
_RUNTIME_COMPONENT_TASK_MARKERS = (
    "compiled extension",
    "compiled extensions",
    "cython extension",
    "cython extensions",
    "native extension",
    "native extensions",
    "c extension",
    "c extensions",
    "dynamic library",
    "dynamic libraries",
    "extension module",
    "extension modules",
    "native module",
    "native modules",
    "runtime module",
    "runtime modules",
    "loadable runtime component",
    "runtime component",
    "runtime components",
    "shared library",
    "shared libraries",
    "plugin entrypoint",
    "plugin host",
    "generated executable",
    "runtime harness",
    "custom runtime",
    "interpreter",
    "simulator",
)
_RUNTIME_COMPONENT_BEHAVIOR_MARKERS = (
    "behavior",
    "behavioral",
    "component-specific",
    "component-specific test",
    "component-specific tests",
    "component test",
    "component tests",
    "callable",
    "extension-specific",
    "entry point",
    "entrypoint",
    "executed",
    "execution smoke",
    "exported function",
    "external verifier",
    "function-level",
    "invokable",
    "invocation",
    "invoke",
    "invoked",
    "non-import",
    "repository test tail",
    "repository-test-tail",
    "specific test",
    "targeted component test",
    "targeted component tests",
    "works in original context",
)
_RUNTIME_COMPONENT_BEHAVIOR_CONTRACT_TERMS = {
    "behavior",
    "behavioral",
    "candidate_final_proof",
    "candidate_runtime_smoke",
    "component",
    "custom_runtime_smoke",
    "external_verifier",
    "repository_tail",
    "runtime",
    "runtime_behavior",
    "smoke",
    "test",
    "tests",
    "verification",
    "verifier",
}
_RUNTIME_COMPONENT_VERIFIER_COMMAND_RE = re.compile(
    r"(?:^|\s)(?:python|pytest|unittest|node|npm|pnpm|yarn|cargo|go|java|ruby|perl|php|lua|julia|Rscript|swift|dotnet|mono)\b"
    r"|(?:^|\s)\./[^\s]+"
    r"|\b(?:test|tests|verify|verifier|smoke|check)\b"
)
_RUNTIME_COMPONENT_CALLABLE_INVOCATION_RE = re.compile(
    r"\b[A-Za-z_][\w.]*\.[A-Za-z_]\w*\s*\("
    r"|\b(?:main|run|execute|invoke|entrypoint|entry_point)\s*\("
)
_RUNTIME_COMPONENT_LOADER_CALL_RE = re.compile(
    r"\b(?:ctypes\.)?(?:CDLL|PyDLL|WinDLL|OleDLL)\s*\("
    r"|\bctypes\.(?:cdll|pydll|windll|oledll)\.LoadLibrary\s*\("
    r"|\bimportlib\.import_module\s*\("
    r"|\b[A-Za-z_][\w.]*\.(?:import_module|load_library|LoadLibrary)\s*\("
    r"|\b(?:import_module|load_library|LoadLibrary)\s*\("
    r"|\b(?:dlopen|ffi\.load|ffi\.dlopen|cffi\.FFI\s*\(\s*\)\.dlopen)\s*\("
)
_RUNTIME_COMPONENT_ENTRYPOINT_EXECUTION_RE = re.compile(
    r"(?:^|\s)(?:node|python|ruby|perl|php|lua|julia|Rscript|swift|java|dotnet|mono)\s+(?!-c\b)[^\s;]+"
    r"|(?:^|\s)\./[^\s]+"
)
_RUNTIME_COMPONENT_NON_BEHAVIOR_COMMAND_RE = re.compile(
    r"\b(?:build|building|configure|configured|install|installed|installing|list|listing|noop|no-op|probe|readback|read-back)\b"
    r"|--help\b|--version\b|(?:^|\s)-h(?:\s|$)|(?:^|\s)-v(?:\s|$)"
)
_RUNTIME_COMPONENT_IMPORT_LOAD_PATH_SIGNAL_RE = re.compile(
    r"\b(?:attribute|exists?|existence|file|hasattr|import(?:ed|s|ing)?|load(?:ed|s|ing)?|metadata|path|which)\b"
    r"|__file__"
    r"|\b(?:ldd|ls|nm|otool|readelf)\b"
    r"|\.(?:so|pyd|dylib|dll|exe)\b"
)
_RUNTIME_COMPONENT_TARGETED_BEHAVIOR_TEST_RE = re.compile(
    r"\b(?:behavior|behaviour|invocation|invoke[sd]?|execution smoke|entrypoint|entry point|callable|function-level)\b"
)
_RUNTIME_COMPONENT_BEHAVIOR_REQUIREMENT_RE = re.compile(
    r"\b(?:work|works|working|compatib\w*|functional(?:ity)?|behavior(?:al)?|run|runs|running|runnable|execute[sd]?|executable|invokable|invocation|invoke[sd]?)\b"
)
_RUNTIME_COMPONENT_DOC_OR_INVESTIGATION_MARKERS = (
    "analyze",
    "diagnose",
    "document",
    "documentation",
    "docs",
    "explain",
    "investigate",
    "readme",
    "report findings",
)
_RUNTIME_COMPONENT_REPAIR_OR_VERIFIER_MARKERS = (
    "exercise",
    "fix",
    "implement",
    "invoke",
    "repair",
    "test",
    "validate",
    "verify",
)
_RUNTIME_COMPONENT_INVOCATION_COMMAND_TOOLS = {
    "dotnet",
    "java",
    "julia",
    "lua",
    "mono",
    "node",
    "perl",
    "php",
    "python",
    "python3",
    "ruby",
    "rscript",
    "swift",
}

_LONG_DEPENDENCY_BUILD_ACTION_MARKERS = (
    "build",
    "compile ",
    "compiled ",
    "compiling ",
    "configure",
    "from source",
    "install",
    "make ",
    "freshly built",
)
_LONG_DEPENDENCY_BUILD_DOMAIN_MARKERS = (
    "apt-get",
    "cargo",
    "cmake",
    "compiler",
    "dependency",
    "dependencies",
    "make ",
    "maven",
    "npm",
    "ocaml",
    "opam",
    "package",
    "pip",
    "source",
    "toolchain",
)
_LONG_DEPENDENCY_ARTIFACT_CONTEXT_MARKERS = (
    "artifact",
    "binary",
    "created",
    "ensure",
    "executable",
    "exists",
    "functional",
    "invoked",
    "invokable",
    "output",
    "produce",
    "through",
    "version",
)
_LONG_DEPENDENCY_ARTIFACT_PROOF_MARKERS = (
    "-version",
    "executable",
    "exists=true",
    "functional smoke",
    "invoked",
    "ls -l",
    "regular file",
    "smoke_ok",
    "test -x",
)
_LONG_DEPENDENCY_ARTIFACT_NEGATIVE_MARKERS = (
    "does not exist",
    "missing",
    "no such file",
    "not found",
)

_STATEFUL_OUTPUT_STATE_MARKERS = (
    "current state",
    "live state",
    "live status",
    "real state",
    "runtime state",
    "runtime status",
    "state object",
    "state payload",
    "store state",
)
_STATEFUL_OUTPUT_SURFACE_MARKERS = (
    "badge",
    "bubble",
    "copy",
    "display",
    "label",
    "message",
    "notification",
    "render",
    "speech",
    "status",
    "text",
    "title",
    "ui",
)
_STATEFUL_OUTPUT_CONNECT_MARKERS = (
    "connect",
    "derive",
    "display",
    "read",
    "reflect",
    "render",
    "show",
    "surface",
    "use",
    "uses",
    "using",
)
_STATEFUL_OUTPUT_POSITIVE_MARKERS = (
    "adapter input",
    "adapter returned",
    "current state",
    "fake live",
    "injected",
    "live path",
    "live state",
    "live-state",
    "mock live",
    "state object",
    "state payload",
)
_STATEFUL_OUTPUT_NEGATIVE_MARKERS = (
    "demo",
    "fixture",
    "fixture path",
    "fallback",
    "non-live",
    "non live",
    "offline",
    "static",
    "without live",
)
_STATEFUL_OUTPUT_NOT_LIVE_MARKERS = (
    "does not claim live",
    "doesn't claim live",
    "not claim live",
    "not live",
    "without claiming live",
)
_STATEFUL_OUTPUT_ASSERTION_MARKERS = (
    "assert",
    "check",
    "expect",
    "pass",
    "prove",
    "test",
    "validat",
    "verify",
)

_EDIT_SCOPE_MARKERS = (
    "allowed edit",
    "allowed edits",
    "do not edit",
    "do not modify",
    "don't edit",
    "don't modify",
    "must not edit",
    "must not modify",
    "only edit",
    "only edits",
    "only change",
    "only changes",
    "only modify",
    "only modification",
    "only replacements",
    "replace words",
    "specified replacement",
    "specified replacements",
    "without editing",
    "without modifying",
)

_ALL_VALID_ANSWER_TASK_MARKERS = (
    "all valid",
    "all winning",
    "all possible",
    "all matching",
    "all legal",
    "multiple valid",
    "multiple winning",
    "multiple possible",
    "print them all",
    "write them all",
    "list them all",
    "one per line",
)

_COMPLETENESS_EVIDENCE_MARKERS = (
    "all legal",
    "all valid",
    "all winning",
    "all possible",
    "both",
    "candidate",
    "complete",
    "completeness",
    "enumerat",
    "exhaust",
    "found all",
    "list them all",
    "mates [",
    "multiple",
    "no other",
    "one per line",
    "winning moves",
)

_NUMERIC_STRONG_TASK_RE = re.compile(
    r"\b("
    r"optimization|optimisation|optimize|optimise|scientific|spectrum|spectra|"
    r"peak|peaks|gamma|amplitude|residual|rmse"
    r")\b",
    re.IGNORECASE,
)
_NUMERIC_FIT_RE = re.compile(r"\b(fit|fitting|fitted)\b", re.IGNORECASE)

_NUMERIC_CHECK_MARKERS = (
    "amplitude",
    "bounds",
    "error",
    "fit",
    "gamma",
    "loss",
    "metric",
    "mse",
    "offset",
    "peak",
    "plausibility",
    "range",
    "residual",
    "rmse",
    "window",
    "x0",
)

_NUMERIC_INDEPENDENCE_MARKERS = (
    "alternative",
    "bootstrap",
    "brute force",
    "compare",
    "comparison",
    "cross check",
    "cross-check",
    "different method",
    "holdout",
    "independent",
    "recalculate",
    "recalculated",
    "recompute",
    "recomputed",
    "second method",
    "sensitivity",
    "stability",
    "validator",
)

_QUERY_ONLY_HIDDEN_MODEL_MARKERS = (
    "a1",
    "hidden layer",
    "matrix",
    "neural network",
    "relu",
)
_QUERY_ONLY_UNKNOWN_MARKERS = (
    "black box",
    "black-box",
    "do not know",
    "don't know",
    "hidden",
    "unknown",
)
_QUERY_ONLY_FORWARD_RE = re.compile(r"\bforward\b(?:\s*\(|\s+function\b)?", re.IGNORECASE)
_QUERY_ONLY_ACCESS_RE = re.compile(
    r"\b(?:access|call|calling|evaluate|evaluating|oracle|query|queries|querying)\b",
    re.IGNORECASE,
)
_QUERY_ONLY_FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(r"\bfrom\s+forward\s+import\s+[^;\n]*(?:\bA1\b|\bA2\b|\bb1\b|\bb2\b)", re.IGNORECASE),
    re.compile(r"\bopen\s*\([^)]*['\"][^'\"]*forward\.py['\"]"),
    re.compile(r"\b(?:Path|pathlib\s*\.\s*Path)\s*\([^)]*['\"][^'\"]*forward\.py['\"][^)]*\)\s*\.\s*read_(?:text|bytes)\s*\("),
    re.compile(r"\binspect\s*\.\s*getsource\s*\("),
)
_QUERY_ONLY_FORWARD_IMPORT_ALIAS_RE = re.compile(
    r"^\s*import\s+forward(?:\s+as\s+([A-Za-z_]\w*))?",
    re.IGNORECASE | re.MULTILINE,
)
_QUERY_ONLY_FORWARD_DYNAMIC_IMPORT_ALIAS_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*(?:importlib\s*\.\s*import_module|__import__)\s*\(\s*['\"]forward['\"]\s*\)",
    re.IGNORECASE,
)
_QUERY_ONLY_INLINE_DYNAMIC_IMPORT_SECRET_RE = re.compile(
    r"(?:"
    r"(?:importlib\s*\.\s*import_module|__import__)\s*\(\s*['\"]forward['\"]\s*\)\s*\.\s*(?:A1|A2|b1|b2)\b"
    r"|"
    r"\b(?:getattr|hasattr)\s*\(\s*(?:importlib\s*\.\s*import_module|__import__)\s*\(\s*['\"]forward['\"]\s*\)\s*,\s*['\"](?:A1|A2|b1|b2)['\"]"
    r")",
    re.IGNORECASE,
)
_QUERY_ONLY_FORWARD_STAR_IMPORT_RE = re.compile(
    r"^\s*from\s+forward\s+import\s+\*",
    re.IGNORECASE | re.MULTILINE,
)
_QUERY_ONLY_SECRET_RE = re.compile(r"\b(?:A1|A2|b1|b2)\b")
_QUERY_ONLY_GENERALIZATION_MARKERS = (
    "different seed",
    "generaliz",
    "holdout",
    "randomized",
    "synthetic",
)
_QUERY_ONLY_GENERALIZATION_SUCCESS_MARKERS = (
    "all matched",
    "hidden pass",
    "holdout pass",
    "pass true",
    "passed",
    "synthetic pass",
)
_QUERY_ONLY_ALL_MATCHED_TRUE_RE = re.compile(r"\ball[_\s-]*matched\b\s*[:=]?\s*(?:true|1|yes)\b", re.IGNORECASE)
_QUERY_ONLY_GENERALIZATION_FAILURE_MARKERS = (
    "did not pass",
    "fail",
    "failed",
    "failure",
    "false",
    "mismatch",
    "not matched",
    "not run",
    "not-run",
    "not tested",
    "not executed",
    "skip",
    "skipped",
)

_MODEL_INFERENCE_SOURCE_MARKERS = (
    ".bpe",
    ".ckpt",
    "checkpoint",
    "model.bin",
    "model weights",
    "tokenizer",
    "vocab.bpe",
    "weights",
)
_MODEL_INFERENCE_ACTION_MARKERS = (
    "arg-max",
    "argmax",
    "continuation",
    "continue the output",
    "decoding",
    "generate",
    "generated tokens",
    "greedy decode",
    "greedy decoding",
    "inference",
    "next token",
    "next tokens",
    "next 20 tokens",
    "sample",
    "sampling",
)
_MODEL_INFERENCE_OUTPUT_MARKERS = (
    "output",
    "print",
    "token",
)
_MODEL_INFERENCE_CHECK_MARKERS = (
    "arg-max",
    "argmax",
    "continuation",
    "continue",
    "generated",
    "inference",
    "output",
    "sample",
    "sampling",
    "token",
)
_MODEL_INFERENCE_ORACLE_MARKERS = (
    "argmax match",
    "argmax token",
    "arg-max match",
    "all matched",
    "candidate_equals_reference",
    "expected continuation",
    "expected_continuation",
    "expected output",
    "golden",
    "ground truth",
    "ground-truth",
    "known continuation",
    "logits match",
    "logits matched",
    "matched reference",
    "matches reference",
    "oracle match",
    "python reference match",
    "reference comparison",
    "reference implementation match",
    "reference model match",
    "reference_output",
    "same tokens",
    "token id match",
    "token ids match",
    "top-1 match",
    "top-1 token",
)
_MODEL_INFERENCE_ORACLE_SUCCESS_MARKERS = (
    "all matched",
    "candidate_equals_reference true",
    "candidate_equals_reference yes",
    "candidate_equals_reference 1",
    "equal",
    "match",
    "matched",
    "pass",
    "passed",
    "same",
    "within tolerance",
)
_MODEL_INFERENCE_CANDIDATE_EQUALS_RE = re.compile(
    r"\bcandidate_equals_reference\b\s*[:=]?\s*(?P<value>[A-Za-z0-9_+-]+)?",
    re.IGNORECASE,
)
_MODEL_INFERENCE_ORACLE_FALSE_VALUE_RE = re.compile(
    r"\b(?:"
    r"all[_\s-]*matched|arg[-\s]?max(?:\s+token)?(?:\s+ids?)?\s+match|"
    r"candidate_equals_reference|equal|equals|logits?\s+match|match(?:es|ed)?|"
    r"matched\s+reference|matches\s+reference|oracle\s+match|pass(?:ed)?|"
    r"python\s+reference\s+match|reference\s+comparison|reference\s+implementation\s+match|"
    r"reference\s+model\s+match|same|token(?:\s+ids?)?\s+match|"
    r"top-1(?:\s+token(?:\s+ids?)?)?\s+match"
    r")\b\s*(?::|=|\bis\b)?\s*"
    r"(?:false\b|no\s+match\b|(?:0|no)\b(?!\s+(?:differences?|errors?|failures?|mismatches?)))",
    re.IGNORECASE,
)
_MODEL_INFERENCE_ZERO_NEGATIVE_COUNT_RE = re.compile(
    r"\b(?:0|no)\s+(?:differences?|errors?|failures?|mismatches?)\b",
    re.IGNORECASE,
)
_MODEL_INFERENCE_SELF_DERIVED_ORACLE_PATTERNS = (
    re.compile(r"\bstandard[-\s]?libm\s+reference\b", re.IGNORECASE),
    re.compile(
        r"\b(?:candidate|current|same)\s+(?:implementation|program|source)\b"
        r".{0,120}\b(?:reference|oracle)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:reference|oracle)\b.{0,120}"
        r"\b(?:candidate|current|same)\s+(?:implementation|program|source)\b",
        re.IGNORECASE | re.DOTALL,
    ),
)
_MODEL_INFERENCE_EPHEMERAL_ORACLE_PATH_RE = re.compile(
    r"/tmp/[^\s'\";|&<>]*(?:expected|golden|oracle|ref|reference|truth)[^\s'\";|&<>]*"
    r"\.(?:c|cc|cpp|cxx|h|hpp|py|rs|go|js|ts|sh|txt|json)\b",
    re.IGNORECASE,
)
_MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE = (
    r"(?P<path>[^'\"\s;|&<>]*(?:expected|golden|oracle|ref|reference|truth)[^'\"\s;|&<>]*"
    r"\.(?:c|cc|cpp|cxx|h|hpp|py|rs|go|js|ts|sh|txt|json))"
)
_MODEL_INFERENCE_GENERATED_ORACLE_TARGET_RE = (
    re.compile(
        r"\bcat\s*>\s*['\"]?" + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE + r"\b.*?<<",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<<\s*['\"]?[A-Za-z0-9_+-]+['\"]?.{0,240}>\s*['\"]?"
        + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE
        + r"\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\btee\s+['\"]?" + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE + r"\b.{0,240}<<",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"<<\s*['\"]?[A-Za-z0-9_+-]+['\"]?.{0,240}\|\s*tee\s+['\"]?"
        + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE
        + r"\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bopen\s*\(\s*['\"]"
        + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE
        + r"['\"]\s*,\s*['\"][^'\"]*w[^'\"]*['\"][^)]*\)"
        r".{0,240}\bwrite\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bPath\s*\(\s*['\"]"
        + _MODEL_INFERENCE_ORACLE_SOURCE_PATH_RE
        + r"['\"]\s*\).{0,120}\bwrite_text\s*\(",
        re.IGNORECASE | re.DOTALL,
    ),
)
_MODEL_INFERENCE_TASK_REFERENCE_COPY_RE = (
    re.compile(
        r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"open\s*\(\s*['\"](?P<src>(?:/tests/|tests/)[^'\"]*)['\"][^)]*\)"
        r"\s*\.read\s*\(\).*?"
        r"open\s*\(\s*['\"](?P<dst>[^'\"]+)['\"]\s*,\s*['\"][^'\"]*w[^'\"]*['\"][^)]*\)"
        r"\s*\.write\s*\(\s*(?P=var)\s*\)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:^|[;&|(\n]\s*)cp\s+['\"]?(?P<src>(?:/tests/|tests/)[^'\"\s]+)['\"]?"
        r"\s+['\"]?(?P<dst>[^'\"\s]+)['\"]?",
        re.IGNORECASE,
    ),
)
_MODEL_INFERENCE_OPEN_READ_WRITE_RE = re.compile(
    r"\bopen\s*\(\s*['\"](?P<src>[^'\"]+\.(?:c|cc|cpp|cxx|py|rs|go))['\"][^)]*\)"
    r"\s*\.read\s*\(\).*?"
    r"\bopen\s*\(\s*['\"](?P<dst>[^'\"]*(?:expected|golden|oracle|ref|reference|truth)[^'\"]*)['\"]",
    re.IGNORECASE | re.DOTALL,
)
_MODEL_INFERENCE_COPY_TO_REF_RE = re.compile(
    r"(?:^|[;&|(\n]\s*)"
    r"(?:cp|copy)\s+['\"]?(?P<src>[^'\"\s]+\.(?:c|cc|cpp|cxx|py|rs|go))['\"]?"
    r"\s+['\"]?(?P<dst>[^'\"\s]*(?:expected|golden|oracle|ref|reference|truth)[^'\"\s]*)['\"]?",
    re.IGNORECASE,
)
_MODEL_INFERENCE_CAT_TO_REF_RE = re.compile(
    r"(?:^|[;&|(\n]\s*)cat\s+['\"]?(?P<src>[^'\"\s]+\.(?:c|cc|cpp|cxx|py|rs|go))['\"]?"
    r"\s*>\s*['\"]?(?P<dst>[^'\"\s]*(?:expected|golden|oracle|ref|reference|truth)[^'\"\s]*)['\"]?",
    re.IGNORECASE,
)
_MODEL_INFERENCE_ORACLE_FAILURE_MARKERS = (
    "assertionerror",
    "different",
    "did not match",
    "fail",
    "failed",
    "false",
    "missing",
    "mismatch",
    "not equal",
    "not found",
    "not match",
    "no match",
    "timed out",
    "timeout",
    "wrong",
    "wrong output",
)
_MODEL_INFERENCE_RATIO_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")

_EXTERNAL_TOOL_REQUIREMENT_MARKERS = (
    "command",
    "executable",
    "flags",
    "tool",
    "validator",
)

_BACKTICK_TEXT_RE = re.compile(r"`([^`]+)`")
_OUTPUT_OF_TOOL_RE = re.compile(
    r"\boutput\s+of\s+(?:[\w.+-]+(?:'s|’s)\s+)?([\w.+-]+)\s+tool\b",
    re.IGNORECASE,
)
_WORDISH_COMMAND_RE = re.compile(r"^[A-Za-z][\w.+-]*$")
_FLAG_RE = re.compile(r"(?<!\S)-[A-Za-z][\w-]*")
_GROUND_TRUTH_RE = re.compile(r"\bground[-\s]+truth\b", re.IGNORECASE)
_COMMAND_EXAMPLE_CONTEXT_RE = re.compile(
    r"\b(?:can\s+run|could\s+run|run|runs|execute|executed|invoke|invoked)\b",
    re.IGNORECASE,
)
_COMMAND_EXAMPLE_PLACEHOLDERS = {"arg", "args", "input", "n", "path", "value"}
_COMMAND_EXAMPLE_OUTPUT_FLAG_TOOLS = {"cc", "clang", "clang++", "gcc", "g++", "rustc"}
_COMMAND_EXAMPLE_SETUP_MUTATION_RE = re.compile(
    r"(?:^|[;&|('\"]\s*)(?:cat|chmod|cp|install|ln|mkdir|mv|rm|touch)\b"
)
_IMPLEMENTATION_CONTRACT_CONTEXT_MARKERS = (
    "along with",
    "corresponding source",
    "existing source",
    "given source",
    "provided",
    "source code",
    "source directory",
)
_IMPLEMENTATION_SOURCE_REF_RE = re.compile(
    r"(?<![\w./-])(?:/[\w.+-]+(?:/[\w.+-]+)*/?|(?:[\w.+-]+/)+[\w.+-]*/?)"
)
_IMPLEMENTATION_SOURCE_GROUNDING_TOOLS = {"glob", "read_file", "run_command", "search_text"}


def _clean_constraint_text(text: object, *, limit: int = 260) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", str(text or "").strip())
    return clip_output(cleaned, limit)


def _constraint_sentences(text: str) -> list[str]:
    normalized = _WHITESPACE_RE.sub(" ", str(text or "").strip())
    if not normalized:
        return []
    pieces = _SENTENCE_BOUNDARY_RE.split(normalized)
    if len(pieces) == 1 and len(normalized) > 320:
        pieces = re.split(r"\s*(?:;|\n|- )\s*", normalized)
    return [_clean_constraint_text(piece) for piece in pieces if _clean_constraint_text(piece)]


def extract_acceptance_constraints(text: object, *, limit: int = 8) -> list[str]:
    """Extract a compact stated-constraint checklist from task text.

    This is intentionally heuristic. The goal is not to solve a task, but to
    keep explicit acceptance and edit-scope constraints visible to the work
    loop so "local verifier passed" is not mistaken for "the task is done".
    """

    constraints: list[str] = []
    for sentence in _constraint_sentences(str(text or "")):
        lowered = sentence.casefold()
        if not any(keyword in lowered for keyword in ACCEPTANCE_CONSTRAINT_KEYWORDS):
            continue
        if sentence not in constraints:
            constraints.append(sentence)
        if len(constraints) >= limit:
            break
    return constraints


def is_edit_scope_constraint(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _EDIT_SCOPE_MARKERS)


def _coerce_evidence_refs(value: object, *, limit: int = 8) -> list[dict]:
    if not isinstance(value, list):
        return []
    refs: list[dict] = []
    for item in value:
        if isinstance(item, int):
            ref = {"kind": "tool_call", "id": item}
        elif isinstance(item, str):
            ids = _evidence_tool_ids(item)
            if not ids:
                continue
            ref = {"kind": "tool_call", "id": ids[0]}
        elif isinstance(item, dict):
            kind = str(item.get("kind") or item.get("type") or "tool_call").strip() or "tool_call"
            raw_id = item.get("id", item.get("tool_call_id"))
            try:
                ref_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            ref = {"kind": kind, "id": ref_id}
        else:
            continue
        if ref not in refs:
            refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def coerce_acceptance_checks(value: object, *, limit: int = 8) -> list[dict]:
    if not isinstance(value, list):
        return []
    checks: list[dict] = []
    for item in value:
        if isinstance(item, str):
            check = {
                "constraint": _clean_constraint_text(item, limit=180),
                "status": "",
                "evidence": "",
            }
        elif isinstance(item, dict):
            check = {
                "constraint": _clean_constraint_text(
                    item.get("constraint") or item.get("criterion") or item.get("name"),
                    limit=180,
                ),
                "status": _clean_constraint_text(item.get("status") or item.get("result"), limit=80),
                "evidence": _clean_constraint_text(item.get("evidence") or item.get("proof"), limit=240),
            }
            evidence_refs = _coerce_evidence_refs(item.get("evidence_refs") or item.get("evidence_ref"))
            if evidence_refs:
                check["evidence_refs"] = evidence_refs
                ref_labels = []
                for ref in evidence_refs:
                    kind = str(ref.get("kind") or "tool_call")
                    if ref.get("id") is None:
                        continue
                    if kind == "tool_call":
                        ref_labels.append(f"tool #{ref.get('id')}")
                    elif kind == "command_evidence":
                        ref_labels.append(f"command evidence #{ref.get('id')}")
                ref_text = " ".join(ref_labels)
                if ref_text and ref_text not in check["evidence"].casefold():
                    check["evidence"] = _clean_constraint_text(
                        f"Evidence refs: {ref_text}. {check['evidence']}".strip(),
                        limit=240,
                    )
        else:
            continue
        if not check["constraint"] and not check["status"] and not check["evidence"]:
            continue
        checks.append(check)
        if len(checks) >= limit:
            break
    return checks


def _completed_tool_calls(session: object) -> list[dict]:
    if not isinstance(session, dict):
        return []
    calls = session.get("tool_calls")
    if not isinstance(calls, list):
        return []
    return [
        call
        for call in calls
        if isinstance(call, dict) and str(call.get("status") or "").casefold() == "completed"
    ]


def _command_evidence_by_id(session: object, evidence_id: int) -> dict | None:
    if not isinstance(session, dict):
        return None
    evidences = session.get("command_evidence")
    if not isinstance(evidences, list):
        return None
    for evidence in evidences:
        if isinstance(evidence, dict) and evidence.get("id") == evidence_id:
            return evidence
    return None


def _command_evidence_ref_summary(evidence: object) -> dict:
    if not isinstance(evidence, dict):
        return {}
    pseudo_call = command_evidence_to_tool_call(evidence)
    ref = tool_call_evidence_ref(pseudo_call)
    ref["kind"] = "command_evidence"
    ref["id"] = evidence.get("id")
    ref["terminal_success"] = bool(evidence.get("terminal_success"))
    return ref


def _latest_completed_write_tool_id(session: object) -> int | None:
    latest: int | None = None
    for call in _completed_tool_calls(session):
        if call.get("tool") not in _WRITE_TOOLS:
            continue
        call_id = call.get("id")
        if isinstance(call_id, int):
            latest = max(latest or call_id, call_id)
    return latest


def _tool_call_by_id(session: object, tool_id: int) -> dict | None:
    for call in _completed_tool_calls(session):
        if call.get("id") == tool_id:
            return call
    return None


def _any_tool_call_by_id(session: object, tool_id: int) -> dict | None:
    if not isinstance(session, dict):
        return None
    calls = session.get("tool_calls")
    if not isinstance(calls, list):
        return None
    for call in calls:
        if isinstance(call, dict) and call.get("id") == tool_id:
            return call
    return None


def _tool_call_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    chunks: list[str] = []
    for key in ("summary", "error"):
        value = call.get(key)
        if value:
            chunks.append(str(value))
    parameters = call.get("parameters")
    if isinstance(parameters, dict):
        for key in ("command", "verify_command", "path", "pattern", "query", "summary", "reason"):
            value = parameters.get(key)
            if value:
                chunks.append(str(value))
    result = call.get("result")
    if isinstance(result, dict):
        for key in ("text", "stdout", "stderr", "summary", "output", "command"):
            value = result.get(key)
            if value:
                chunks.append(str(value))
        argv = result.get("argv")
        if isinstance(argv, list):
            chunks.append(" ".join(str(item) for item in argv))
    elif result:
        chunks.append(str(result))
    return "\n".join(chunks)


def _tool_call_result_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    result = call.get("result")
    chunks: list[str] = []
    if isinstance(result, dict):
        if result.get("exit_code") not in (None, 0):
            return ""
        for key in ("text", "stdout", "stderr", "summary", "output"):
            value = result.get(key)
            if value:
                chunks.append(str(value))
    elif result:
        chunks.append(str(result))
    return "\n".join(chunks)


def _normalized_command_text(text: object) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "").casefold()).strip()


def _tool_call_external_command_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    chunks: list[str] = []
    parameters = call.get("parameters")
    if isinstance(parameters, dict):
        for key in ("command", "verify_command"):
            value = parameters.get(key)
            if value:
                chunks.append(str(value))
    result = call.get("result")
    if isinstance(result, dict):
        value = result.get("command")
        if value:
            chunks.append(str(value))
        argv = result.get("argv")
        if isinstance(argv, list):
            chunks.append(" ".join(str(item) for item in argv))
    return _normalized_command_text("\n".join(chunks))


def _runtime_fresh_run_context(text: object) -> bool:
    text = str(text or "")
    lowered = text.casefold()
    if not any(marker in lowered for marker in _RUNTIME_FRESH_RUN_MARKERS):
        return False
    if not any(marker in lowered for marker in _RUNTIME_ARTIFACT_GENERATION_MARKERS):
        return False
    return True


def is_runtime_visual_artifact_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not _runtime_fresh_run_context(lowered):
        return False
    if not any(marker in lowered for marker in _RUNTIME_VISUAL_ARTIFACT_MARKERS):
        return False
    return any(marker in lowered for marker in _RUNTIME_VISUAL_ARTIFACT_QUALITY_TASK_MARKERS)


def _runtime_tmp_artifacts_in_text(text: object, limit: int = 6) -> list[str]:
    artifacts: list[str] = []
    for match in _RUNTIME_TMP_ARTIFACT_RE.finditer(str(text or "")):
        artifact = str(match.group(1) or "").rstrip("`'\".,;:)")
        if artifact and artifact not in artifacts:
            artifacts.append(artifact)
        if len(artifacts) >= limit:
            break
    return artifacts


def _runtime_tmp_artifact_has_generation_context(text: object, artifact: str) -> bool:
    value = str(text or "")
    if not artifact:
        return False
    lowered_artifact = artifact.casefold()
    for match in _RUNTIME_TMP_ARTIFACT_RE.finditer(value):
        candidate = str(match.group(1) or "").rstrip("`'\".,;:)")
        if candidate.casefold() != lowered_artifact:
            continue
        context = _path_context(value, match.start(), match.end()).casefold()
        if any(
            marker in context
            for marker in (*_RUNTIME_ARTIFACT_CREATED_MARKERS, *_RUNTIME_ARTIFACT_EXPECTED_PATH_MARKERS)
        ):
            return True
    return False


def _runtime_tmp_artifact_is_verifier_scratch_path(artifact: str) -> bool:
    lowered = str(artifact or "").casefold()
    if not lowered.startswith("/tmp/") or not lowered.endswith((".log", ".txt", ".out", ".stdout", ".stderr")):
        return False
    name = lowered.rsplit("/", 1)[-1]
    return any(token in name for token in ("log", "out", "stdout", "stderr", "trace", "transcript"))


def _runtime_fresh_run_artifacts(task_description: object) -> list[str]:
    text = str(task_description or "")
    if "/tmp/" not in text.casefold():
        return []
    if not _runtime_fresh_run_context(text):
        return []
    return _runtime_tmp_artifacts_in_text(text)


def _runtime_fresh_run_artifacts_for_finish(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> list[str]:
    task_text = str(task_description or "")
    if not _runtime_fresh_run_context(task_text):
        return []
    artifacts = _runtime_fresh_run_artifacts(task_text)
    for check in checks:
        for artifact in _runtime_tmp_artifacts_in_text(f"{check.get('constraint') or ''}\n{check.get('evidence') or ''}"):
            if artifact not in artifacts:
                artifacts.append(artifact)
    if isinstance(session, dict):
        for call in _completed_tool_calls(session):
            text = _tool_call_text(call)
            lowered = text.casefold()
            if not any(
                marker in lowered
                for marker in (*_RUNTIME_ARTIFACT_CREATED_MARKERS, *_RUNTIME_ARTIFACT_EXPECTED_PATH_MARKERS)
            ):
                continue
            for artifact in _runtime_tmp_artifacts_in_text(text):
                if _runtime_tmp_artifact_is_verifier_scratch_path(artifact):
                    continue
                if not _runtime_tmp_artifact_has_generation_context(text, artifact):
                    continue
                if artifact not in artifacts:
                    artifacts.append(artifact)
    return artifacts[:6]


def _runtime_artifact_created_by_call(call: object, artifact: str) -> bool:
    if not isinstance(call, dict) or call.get("tool") not in {"run_command", "run_tests"}:
        return False
    if _runtime_artifact_created_by_structured_evidence(call, artifact):
        return True
    text = _tool_call_text(call)
    lowered = text.casefold()
    if artifact.casefold() not in lowered:
        return False
    if "exists=false" in lowered and not any(marker in lowered for marker in _RUNTIME_ARTIFACT_CREATED_MARKERS):
        return False
    return any(marker in lowered for marker in _RUNTIME_ARTIFACT_CREATED_MARKERS)


def _runtime_artifact_created_by_structured_evidence(call: object, artifact: str) -> bool:
    if not isinstance(call, dict):
        return False
    result = call.get("result")
    if not isinstance(result, dict):
        return False
    verifier = result.get("verifier_evidence")
    if isinstance(verifier, dict) and str(verifier.get("verdict") or "").casefold() not in {"pass", "partial"}:
        return False
    artifact_lower = str(artifact or "").casefold()
    if not artifact_lower:
        return False
    artifact_evidence = result.get("artifact_evidence")
    if not isinstance(artifact_evidence, list):
        return False
    for item in artifact_evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").casefold() != "passed":
            continue
        candidates = [
            str(item.get("artifact_id") or ""),
            str(item.get("path") or ""),
            str(item.get("artifact_path") or ""),
        ]
        if any(candidate and candidate.casefold() == artifact_lower for candidate in candidates):
            return True
    return False


def _runtime_artifact_cleanup_by_call(call: object, artifact: str) -> bool:
    if not isinstance(call, dict) or call.get("tool") not in {"run_command", "run_tests"}:
        return False
    text = _tool_call_text(call)
    lowered = text.casefold()
    if artifact.casefold() not in lowered:
        return False
    cleanup_pos = max((lowered.rfind(marker) for marker in _RUNTIME_ARTIFACT_CLEANUP_MARKERS), default=-1)
    if cleanup_pos < 0:
        return False
    created_pos = max((lowered.rfind(marker) for marker in _RUNTIME_ARTIFACT_CREATED_MARKERS), default=-1)
    return created_pos < 0 or cleanup_pos > created_pos


def _latest_runtime_artifact_creation_call(session: object, artifact: str) -> dict | None:
    latest: dict | None = None
    for call in _completed_tool_calls(session):
        if _runtime_artifact_created_by_call(call, artifact):
            latest = call
    return latest


def _has_runtime_artifact_cleanup_after(session: object, artifact: str, after_tool_id: object) -> bool:
    try:
        after_id = int(after_tool_id)
    except (TypeError, ValueError):
        after_id = -1
    for call in _completed_tool_calls(session):
        try:
            call_id = int(call.get("id"))
        except (TypeError, ValueError):
            continue
        if call_id <= after_id:
            continue
        if _runtime_artifact_cleanup_by_call(call, artifact):
            return True
    return False


def _runtime_artifact_freshness_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    artifacts = _runtime_fresh_run_artifacts_for_finish(task_description, checks, session)
    if not artifacts or not isinstance(session, dict):
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "stateful output semantic contrast evidence missing: tasks that connect "
            "user-facing copy, labels, messages, or status text to live/current state "
            "must cite a positive injected-state assertion and a negative fixture, "
            "demo, static, or fallback assertion before task_done=true; label-only "
            "or relabel-only verifier evidence is not enough"
        )
    for artifact in artifacts:
        creation_call = _latest_runtime_artifact_creation_call(session, artifact)
        if not creation_call:
            continue
        if _has_runtime_artifact_cleanup_after(session, artifact, creation_call.get("id")):
            continue
        return (
            f"runtime artifact freshness unchecked: {artifact} was created during self-verification; "
            "if the external verifier is expected to create runtime artifacts from a fresh run, "
            "preserve the proof in acceptance_checks but clean stale runtime artifacts before task_done=true"
        )
    return ""


def _has_runtime_artifact_grounding_evidence(evidence: object, session: object, artifact: str) -> bool:
    for call in _evidence_command_calls(evidence, session):
        if call and _runtime_artifact_created_by_call(call, artifact):
            return True
    return False


def _runtime_artifact_final_state_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    artifacts = _runtime_fresh_run_artifacts_for_finish(task_description, checks, session)
    if not artifacts or not isinstance(session, dict):
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "runtime final verifier artifact evidence missing: fresh runtime tasks "
            "must cite the final verifier-shaped run and expected /tmp artifact "
            "creation before task_done=true"
        )
    for artifact in artifacts:
        matching_checks = [
            check
            for check in verified_checks
            if artifact.casefold()
            in f"{check.get('constraint') or ''}\n{check.get('evidence') or ''}".casefold()
        ]
        if not matching_checks:
            return (
                "runtime final verifier artifact evidence missing: "
                f"{artifact} must be verified by a completed final verifier-shaped run "
                "before task_done=true"
            )
        if any(_has_runtime_artifact_grounding_evidence(check, session, artifact) for check in matching_checks):
            continue
        return (
            "runtime final verifier artifact evidence ungrounded: "
            f"{artifact} checks must cite a completed run_command or run_tests tool "
            "whose output proves the artifact was created during the verifier-shaped run"
        )
    return ""


def _has_runtime_visual_artifact_quality_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _RUNTIME_VISUAL_ARTIFACT_QUALITY_EVIDENCE_MARKERS)


def _has_runtime_visual_artifact_quality_evidence(evidence: object, session: object) -> bool:
    if not _has_runtime_visual_artifact_quality_marker(_evidence_semantic_text(evidence)):
        return False
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in _GROUNDING_TOOLS:
            continue
        if _has_runtime_visual_artifact_quality_marker(_tool_call_text(call)):
            return True
    return False


def _runtime_visual_artifact_quality_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_runtime_visual_artifact_task(task_description):
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    visual_checks = [
        check
        for check in verified_checks
        if any(
            marker
            in f"{check.get('constraint') or ''}\n{check.get('evidence') or ''}".casefold()
            for marker in _RUNTIME_VISUAL_ARTIFACT_MARKERS
        )
    ]
    if not visual_checks:
        return (
            "runtime visual artifact quality evidence missing: rendered frame, screenshot, "
            "or image tasks with expected/correct output must cite expected dimensions, "
            "reference similarity, or explicit expected-output markers before task_done=true"
        )
    if any(_has_runtime_visual_artifact_quality_evidence(check, session) for check in visual_checks):
        return ""
    return (
        "runtime visual artifact quality evidence ungrounded: artifact existence, "
        "nonzero pixels, valid headers, or self-consistent dimensions are not enough; "
        "cite a completed grounding tool whose output checks expected dimensions, "
        "reference similarity, or explicit expected-output markers"
    )


def is_long_dependency_toolchain_build_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _LONG_DEPENDENCY_BUILD_ACTION_MARKERS):
        return False
    return any(marker in lowered for marker in _LONG_DEPENDENCY_BUILD_DOMAIN_MARKERS)


def _path_context(text: str, start: int, end: int, *, radius: int = 80) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def long_dependency_final_artifacts(text: object, *, limit: int = 6) -> list[str]:
    value = str(text or "")
    if not is_long_dependency_toolchain_build_task(value):
        return []
    artifacts: list[str] = []
    for match in _ABSOLUTE_PATH_RE.finditer(value):
        if match.start() > 0 and re.match(r"[A-Za-z0-9_-]", value[match.start() - 1]):
            continue
        path = str(match.group(1) or "").rstrip("`'\".,;:)")
        if not path or path.endswith("/"):
            continue
        context = _path_context(value, match.start(), match.end()).casefold()
        if re.search(r"\b(?:under|inside|within|in)\s+" + re.escape(path.casefold()) + r"\b", context):
            continue
        if not any(marker in context for marker in _LONG_DEPENDENCY_ARTIFACT_CONTEXT_MARKERS):
            continue
        if path not in artifacts:
            artifacts.append(path)
        if len(artifacts) >= limit:
            break
    return artifacts


def _long_dependency_artifact_proved_by_text(text: object, artifact: str) -> bool:
    lowered = str(text or "").casefold()
    artifact_lower = str(artifact or "").casefold()
    if not artifact_lower or artifact_lower not in lowered:
        return False
    if any(marker in lowered for marker in _LONG_DEPENDENCY_ARTIFACT_NEGATIVE_MARKERS):
        return False
    return any(marker in lowered for marker in _LONG_DEPENDENCY_ARTIFACT_PROOF_MARKERS)


def _has_long_dependency_artifact_evidence(evidence: object, session: object, artifact: str) -> bool:
    if isinstance(evidence, dict):
        evidence_text = "\n".join(
            str(evidence.get(key) or "") for key in ("constraint", "evidence", "proof") if evidence.get(key)
        )
        refs = _check_evidence_refs(evidence)
    else:
        evidence_text = str(evidence or "")
        refs = [{"kind": "tool_call", "id": tool_id} for tool_id in _evidence_tool_ids(evidence)]
    text_proves_artifact = _long_dependency_artifact_proved_by_text(evidence_text, artifact)
    text_names_artifact = str(artifact or "").casefold() in evidence_text.casefold()
    if not text_proves_artifact and not text_names_artifact:
        return False
    for ref in refs:
        ref_id = ref.get("id")
        if ref_id is None:
            continue
        kind = str(ref.get("kind") or "tool_call")
        if kind == "command_evidence":
            command_evidence = _command_evidence_by_id(session, ref_id)
            if command_evidence and long_dependency_artifact_proven_by_command_evidence(command_evidence, artifact):
                return True
            continue
        if kind == "tool_call":
            call = _any_tool_call_by_id(session, ref_id)
            if not call or call.get("tool") not in {"run_command", "run_tests"}:
                continue
            if long_dependency_artifact_proven_by_call(call, artifact):
                return True
    return False


def _long_dependency_build_artifact_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    artifacts = long_dependency_final_artifacts(task_description)
    if not artifacts:
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "long dependency/toolchain final artifact evidence missing: source-build "
            "tasks must cite completed tool output proving the required final executable "
            "or artifact exists, is invokable/executable, or passed a smoke command"
        )
    missing = [
        artifact
        for artifact in artifacts
        if not any(_has_long_dependency_artifact_evidence(check, session, artifact) for check in verified_checks)
    ]
    if not missing:
        return ""
    return (
        "long dependency/toolchain final artifact evidence ungrounded: prerequisite "
        "installation, configure, dependency generation, or partial build progress is "
        "not completion; cite a completed tool proving "
        f"{', '.join(missing[:3])} exists and is executable/invokable"
    )


def is_runtime_component_behavior_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _RUNTIME_COMPONENT_TASK_MARKERS):
        return False
    has_doc_or_investigation_marker = any(
        re.search(rf"\b{re.escape(marker)}\b", lowered)
        for marker in _RUNTIME_COMPONENT_DOC_OR_INVESTIGATION_MARKERS
    )
    has_repair_or_verifier_marker = any(
        re.search(rf"\b{re.escape(marker)}\b", lowered)
        for marker in _RUNTIME_COMPONENT_REPAIR_OR_VERIFIER_MARKERS
    )
    if has_doc_or_investigation_marker and not has_repair_or_verifier_marker:
        return False
    return bool(_RUNTIME_COMPONENT_BEHAVIOR_REQUIREMENT_RE.search(lowered))


def _runtime_component_evidence_texts(check: object, session: object) -> list[str]:
    texts = []
    if isinstance(check, dict):
        texts.append(str(check.get("constraint") or ""))
        texts.append(str(check.get("evidence") or ""))
    for call in _evidence_command_calls(check, session):
        texts.append(_tool_call_text(call))
    return [text for text in texts if str(text or "").strip()]


def _runtime_component_call_contract_terms(call: object) -> set[str]:
    if not isinstance(call, dict):
        return set()
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    contract = parameters.get("execution_contract") if isinstance(parameters.get("execution_contract"), dict) else {}
    terms: set[str] = set()
    for key in ("purpose", "stage", "proof_role", "acceptance_kind", "risk_class"):
        value = contract.get(key)
        if isinstance(value, str):
            terms.update(re.findall(r"[a-zA-Z0-9_]+", value.casefold()))
        elif isinstance(value, list):
            for item in value:
                terms.update(re.findall(r"[a-zA-Z0-9_]+", str(item).casefold()))
    return terms


def _runtime_component_command_kind_allows_behavior(call: object) -> bool:
    if not isinstance(call, dict):
        return False
    tool = call.get("tool")
    if tool == "run_tests":
        return True
    if tool != "run_command":
        return False
    if _runtime_component_call_contract_terms(call) & _RUNTIME_COMPONENT_BEHAVIOR_CONTRACT_TERMS:
        return True
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    command = str(parameters.get("command") or "")
    return bool(_RUNTIME_COMPONENT_VERIFIER_COMMAND_RE.search(command))


def _runtime_component_callable_invocation_seen(call: object) -> bool:
    if not isinstance(call, dict):
        return False
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    command = str(parameters.get("command") or "")
    if re.search(r"\b(?:getattr|hasattr)\s*\(|(?:^|[.\s])load\s*\(", command):
        return False
    if _RUNTIME_COMPONENT_LOADER_CALL_RE.search(command):
        return False
    return bool(_RUNTIME_COMPONENT_CALLABLE_INVOCATION_RE.search(command))


def _runtime_component_import_load_path_signal_seen(call: object, text: str) -> bool:
    if not isinstance(call, dict):
        return False
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    command = str(parameters.get("command") or "")
    return bool(_RUNTIME_COMPONENT_IMPORT_LOAD_PATH_SIGNAL_RE.search(f"{command}\n{text}".casefold()))


def _runtime_component_targeted_behavior_test_seen(call: object, text: str) -> bool:
    if not isinstance(call, dict) or call.get("tool") != "run_tests":
        return False
    normalized_text = text.replace("_", " ")
    if not _RUNTIME_COMPONENT_TARGETED_BEHAVIOR_TEST_RE.search(normalized_text):
        return False
    return any(
        marker in normalized_text
        for marker in (
            "component",
            "component-specific",
            "runtime",
            "targeted",
            "test ",
            "::test",
        )
    )


def _runtime_component_repository_tail_behavior_seen(text: str) -> bool:
    if "repository-test-tail" not in text and "repository test tail" not in text:
        return False
    return bool(_RUNTIME_COMPONENT_TARGETED_BEHAVIOR_TEST_RE.search(text.replace("_", " ")))


def _runtime_component_external_verifier_behavior_seen(call: object, text: str) -> bool:
    terms = _runtime_component_call_contract_terms(call)
    if "external_verifier" not in terms:
        return False
    return any(
        marker in text
        for marker in (
            "behavior",
            "behaviour",
            "callable",
            "entrypoint",
            "entry point",
            "executed",
            "execution smoke",
            "function-level",
            "invocation",
            "invoked",
            "runtime behavior",
        )
    )


def _runtime_component_execution_smoke_seen(call: object, text: str) -> bool:
    if not isinstance(call, dict) or call.get("tool") not in {"run_command", "run_tests"}:
        return False
    if _runtime_component_call_contract_terms(call) & {
        "candidate_runtime_smoke",
        "custom_runtime_smoke",
        "runtime_behavior",
    }:
        return True
    return any(marker in text for marker in ("executed", "execution smoke", "entrypoint", "entry point"))


def _runtime_component_non_behavior_command_shape_seen(call: object, text: str) -> bool:
    if not isinstance(call, dict):
        return False
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    command = str(parameters.get("command") or "")
    return bool(_RUNTIME_COMPONENT_NON_BEHAVIOR_COMMAND_RE.search(f"{command}\n{text}".casefold()))


def _runtime_component_entrypoint_behavior_signal_seen(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "behavior",
            "behaviour",
            "executed",
            "execution smoke",
            "invocation",
            "invoked",
            "ran ",
            "run ",
            "runs",
            "runtime behavior",
        )
    )


def _runtime_component_entrypoint_execution_seen(call: object) -> bool:
    if not isinstance(call, dict) or call.get("tool") not in {"run_command", "run_tests"}:
        return False
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    command = str(parameters.get("command") or "")
    if re.search(r"\b(?:pytest|unittest|tox|nox)\b", command):
        return False
    return bool(_RUNTIME_COMPONENT_ENTRYPOINT_EXECUTION_RE.search(command))


def _runtime_component_call_text_proves_behavior(call: object, proof_text: object = "") -> bool:
    if not isinstance(call, dict):
        return False
    text = _tool_call_text(call).casefold()
    if not text:
        return False
    proof_text = str(proof_text or "").casefold()
    combined_text = f"{text}\n{proof_text}"
    callable_invocation = _runtime_component_callable_invocation_seen(call)
    targeted_test = _runtime_component_targeted_behavior_test_seen(call, text)
    repository_tail = _runtime_component_repository_tail_behavior_seen(text)
    execution_smoke = _runtime_component_execution_smoke_seen(call, text)
    non_behavior_entrypoint = _runtime_component_non_behavior_command_shape_seen(call, combined_text)
    entrypoint_execution = (
        _runtime_component_entrypoint_execution_seen(call)
        and not non_behavior_entrypoint
        and _runtime_component_entrypoint_behavior_signal_seen(text)
    )
    import_load_path_signal = _runtime_component_import_load_path_signal_seen(call, text)
    external_verifier = _runtime_component_external_verifier_behavior_seen(call, text) and not import_load_path_signal
    import_load_path_only = import_load_path_signal and not (
        callable_invocation or targeted_test or repository_tail or execution_smoke
    )
    if import_load_path_only:
        return False
    return bool(
        callable_invocation
        or targeted_test
        or repository_tail
        or execution_smoke
        or entrypoint_execution
        or external_verifier
    )


def _runtime_component_has_behavior_evidence(check: object, session: object) -> bool:
    claim_text = "\n".join(_runtime_component_evidence_texts(check, None)).casefold()
    if not claim_text and not _check_evidence_refs(check):
        return False
    for ref in _check_evidence_refs(check):
        ref_id = ref.get("id")
        if ref_id is None:
            continue
        kind = str(ref.get("kind") or "tool_call")
        if kind == "command_evidence":
            evidence = _command_evidence_by_id(session, ref_id)
            if not evidence or not evidence.get("terminal_success"):
                continue
            call = command_evidence_to_tool_call(evidence)
            if _runtime_component_command_kind_allows_behavior(call) and _runtime_component_call_text_proves_behavior(
                call,
                claim_text,
            ):
                return True
            continue
        if kind != "tool_call":
            continue
        call = _tool_call_by_id(session, ref_id)
        if not call:
            continue
        if call.get("tool") not in {"run_command", "run_tests"}:
            continue
        if not tool_call_terminal_success(call):
            continue
        if _runtime_component_command_kind_allows_behavior(call) and _runtime_component_call_text_proves_behavior(
            call,
            claim_text,
        ):
            return True
    return False


def _runtime_component_invocation_command_requirements(text: object, *, limit: int = 4) -> list[str]:
    source = str(text or "")
    requirements: list[str] = []
    for match in _BACKTICK_TEXT_RE.finditer(source):
        value = _clean_constraint_text(match.group(1), limit=240)
        if not value:
            continue
        context = source[max(0, match.start() - 80) : min(len(source), match.end() + 80)].casefold()
        if not re.search(r"\b(?:run|runs|running|execute|executes|invok(?:e|es|ing))\b", context):
            continue
        try:
            tokens = shlex.split(value)
        except ValueError:
            tokens = value.split()
        if len(tokens) < 2:
            continue
        if tokens[0].casefold() not in _RUNTIME_COMPONENT_INVOCATION_COMMAND_TOOLS:
            continue
        target = tokens[1]
        if target.startswith("-") or not re.match(r"^(?:[\w.+/-]+|/[\w.+/-]+)$", target):
            continue
        if value not in requirements:
            requirements.append(value)
        if len(requirements) >= limit:
            break
    return requirements


def _runtime_component_invocation_command_grounded(
    task_description: object,
    verified_checks: list[dict[str, str]],
    session: object,
) -> bool:
    requirements = _runtime_component_invocation_command_requirements(task_description)
    if not requirements or not verified_checks:
        return False
    return all(
        any(_has_exact_command_example_evidence(check, session, command) for check in verified_checks)
        for command in requirements
    )


def _runtime_component_behavior_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_runtime_component_behavior_task(task_description):
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if _runtime_component_invocation_command_grounded(task_description, verified_checks, session):
        return ""
    if any(_runtime_component_has_behavior_evidence(check, session) for check in verified_checks):
        return ""
    return (
        "runtime component behavior evidence import-only: for loadable runtime "
        "components that must work, successful build, import, load, or path proof is "
        "not enough; cite a completed command that invokes component behavior or "
        "component-specific tests in the original runtime context"
    )


def is_stateful_output_semantic_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not lowered:
        return False
    if not any(marker in lowered for marker in _STATEFUL_OUTPUT_STATE_MARKERS):
        return False
    if not any(marker in lowered for marker in _STATEFUL_OUTPUT_SURFACE_MARKERS):
        return False
    return any(marker in lowered for marker in _STATEFUL_OUTPUT_CONNECT_MARKERS)


def _has_stateful_output_assertion_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _STATEFUL_OUTPUT_ASSERTION_MARKERS)


def _stateful_output_evidence_texts(checks: list[dict[str, str]], session: object) -> list[str]:
    texts: list[str] = []
    for check in checks:
        for call in _evidence_command_calls(check, session):
            if call and call.get("tool") in {"run_command", "run_tests"}:
                result = call.get("result")
                if isinstance(result, dict) and result.get("exit_code") not in (None, 0):
                    continue
                chunks: list[str] = []
                if isinstance(result, dict):
                    for key in ("text", "stdout", "stderr", "summary", "output"):
                        value = result.get(key)
                        if value:
                            chunks.append(str(value))
                elif result:
                    chunks.append(str(result))
                if chunks:
                    texts.append("\n".join(chunks))
    return texts


def _has_stateful_output_positive_evidence(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _STATEFUL_OUTPUT_POSITIVE_MARKERS):
        return False
    return _has_stateful_output_assertion_marker(lowered)


def _has_stateful_output_negative_evidence(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _STATEFUL_OUTPUT_NEGATIVE_MARKERS):
        return False
    if any(marker in lowered for marker in _STATEFUL_OUTPUT_NOT_LIVE_MARKERS):
        return _has_stateful_output_assertion_marker(lowered)
    return "live" not in lowered and _has_stateful_output_assertion_marker(lowered)


def _stateful_output_semantic_contrast_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_stateful_output_semantic_task(task_description):
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "stateful output semantic contrast evidence missing: tasks that connect "
            "user-facing copy, labels, messages, or status text to live/current state "
            "must cite a positive injected-state assertion and a negative fixture, "
            "demo, static, or fallback assertion before task_done=true; label-only "
            "or relabel-only verifier evidence is not enough"
        )
    evidence_texts = _stateful_output_evidence_texts(verified_checks, session)
    has_positive = any(_has_stateful_output_positive_evidence(text) for text in evidence_texts)
    has_negative = any(_has_stateful_output_negative_evidence(text) for text in evidence_texts)
    if has_positive and has_negative:
        return ""
    return (
        "stateful output semantic contrast evidence missing: tasks that connect "
        "user-facing copy, labels, messages, or status text to live/current state "
        "must cite a positive injected-state assertion and a negative fixture, "
        "demo, static, or fallback assertion before task_done=true; label-only "
        "or relabel-only verifier evidence is not enough"
    )


def _external_command_text_contains_term(command_text: str, term: object) -> bool:
    normalized = _normalized_command_text(term)
    if not normalized:
        return True
    if normalized.startswith("-") and " " in normalized:
        flag, value = normalized.split(None, 1)
        flag_pattern = re.escape(flag)
        value_pattern = re.escape(value)
        shell_pattern = rf"(?<!\S){flag_pattern}\s+{value_pattern}(?![\w.+-])"
        python_list_pattern = rf"['\"]{flag_pattern}['\"]\s*,\s*['\"]{value_pattern}['\"]"
        return bool(re.search(shell_pattern, command_text) or re.search(python_list_pattern, command_text))
    if normalized.startswith("-"):
        pattern = rf"(?<!\S){re.escape(normalized)}(?![\w.+-])"
        python_list_pattern = rf"['\"]{re.escape(normalized)}['\"]"
        return bool(re.search(pattern, command_text) or re.search(python_list_pattern, command_text))
    pattern = rf"(?<![\w.+-])(?:[\w./+-]*/)?{re.escape(normalized)}(?![\w.+-])"
    return bool(re.search(pattern, command_text))


def _looks_like_command_example(value: str, context: str) -> bool:
    if not _COMMAND_EXAMPLE_CONTEXT_RE.search(context):
        return False
    try:
        tokens = shlex.split(value)
    except ValueError:
        tokens = value.split()
    if not tokens:
        return False
    first = tokens[0]
    if first.startswith(("-", "{", "$")):
        return False
    if not re.match(r"^(?:[\w.+/-]+|/[\w.+/-]+)$", first):
        return False
    return any(token in {"&&", "||"} or token.startswith(("-", "/", ".")) for token in tokens[1:])


def exact_command_example_requirements(text: object, *, limit: int = 4) -> list[dict[str, str]]:
    source = str(text or "")
    requirements: list[dict[str, str]] = []
    for match in _BACKTICK_TEXT_RE.finditer(source):
        value = _clean_constraint_text(match.group(1), limit=240)
        if not value:
            continue
        context = source[max(0, match.start() - 80) : min(len(source), match.end() + 80)]
        if not _looks_like_command_example(value, context):
            continue
        if any(item["command"] == value for item in requirements):
            continue
        requirements.append({"command": value, "sentence": _clean_constraint_text(context, limit=260)})
        if len(requirements) >= limit:
            break
    return requirements


def _clean_source_ref(value: object) -> str:
    return str(value or "").strip().strip(".,;:()[]{}<>\"'")


def _looks_like_source_ref(value: str) -> bool:
    ref = _clean_source_ref(value)
    if ref.startswith("./"):
        ref = ref[2:]
    if not ref or any(ch.isspace() for ch in ref):
        return False
    lowered = ref.casefold()
    if lowered.startswith(("http://", "https://")):
        return False
    if any(ch in ref for ch in ("*", "$", "`", "|", "&", ";")):
        return False
    return "/" in ref


def _implementation_source_refs(sentence: str) -> list[str]:
    refs: list[str] = []
    for value in _BACKTICK_TEXT_RE.findall(sentence):
        ref = _clean_source_ref(value)
        if _looks_like_source_ref(ref) and ref not in refs:
            refs.append(ref)
    for match in _IMPLEMENTATION_SOURCE_REF_RE.finditer(sentence):
        ref = _clean_source_ref(match.group(0))
        if _looks_like_source_ref(ref) and ref not in refs:
            refs.append(ref)
    return refs


def implementation_contract_source_requirements(text: object, *, limit: int = 6) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    for sentence in _constraint_sentences(str(text or "")):
        lowered = sentence.casefold()
        if not any(marker in lowered for marker in _IMPLEMENTATION_CONTRACT_CONTEXT_MARKERS):
            continue
        for ref in _implementation_source_refs(sentence):
            if any(item["path"] == ref for item in requirements):
                continue
            requirements.append({"path": ref, "sentence": sentence})
            if len(requirements) >= limit:
                return requirements
    return requirements


def _source_ref_variants(ref: object) -> list[str]:
    source = _clean_source_ref(ref).casefold()
    if not source:
        return []
    candidates = [source]
    stripped = source.rstrip("/")
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    if source.startswith("/app/"):
        app_relative = source[len("/app/") :]
        for candidate in (app_relative, app_relative.rstrip("/")):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    basename = stripped.rsplit("/", 1)[-1] if stripped else ""
    if basename and basename not in candidates:
        candidates.append(basename)
    return candidates


def _source_ref_matches_text(ref: object, text: object) -> bool:
    normalized_text = _normalized_command_text(text)
    if not normalized_text:
        return False
    for variant in _source_ref_variants(ref):
        if not variant:
            continue
        if variant.endswith("/") and variant in normalized_text:
            return True
        pattern = rf"(?<![\w.+-]){re.escape(variant)}(?:/|\b)"
        if re.search(pattern, normalized_text):
            return True
    return False


def implementation_source_ref_matches_text(ref: object, text: object) -> bool:
    """Return whether text grounds an implementation source/binary reference."""
    return _source_ref_matches_text(ref, text)


def _has_implementation_source_grounding_evidence(evidence: object, session: object, source_ref: object) -> bool:
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in _IMPLEMENTATION_SOURCE_GROUNDING_TOOLS:
            continue
        if _source_ref_matches_text(source_ref, _tool_call_text(call)):
            return True
    return False


def _implementation_contract_source_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    requirements = implementation_contract_source_requirements(task_description)
    if not requirements:
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "implementation contract source evidence missing: hard implementation tasks "
            "with provided source, binaries, or artifacts must cite completed source "
            "grounding before task_done=true"
        )
    for requirement in requirements:
        source_ref = requirement.get("path")
        if any(
            _has_implementation_source_grounding_evidence(check, session, source_ref)
            for check in verified_checks
        ):
            continue
        return (
            "implementation contract source evidence ungrounded: provided source or "
            f"artifact {source_ref} must be grounded by cited read/search/command evidence "
            "before task_done=true"
        )
    return ""


def _command_example_regex(command: str) -> re.Pattern[str] | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return None
    pieces: list[str] = []
    for token in tokens:
        normalized = token.casefold()
        if normalized in _COMMAND_EXAMPLE_PLACEHOLDERS:
            pieces.append(r"\S+")
            continue
        pieces.append(re.escape(normalized))
    if not pieces:
        return None
    # Match the advertised shell command shape with concrete placeholder values.
    # Verifier loops are useful smoke tests, but they are not evidence that the
    # exact user-facing invocation works.
    return re.compile(r"(?<![\w./+-])" + r"\s+".join(pieces) + r"(?![\w./+-])")


def _command_example_call_matches(call: object, command: str) -> bool:
    result = call.get("result") if isinstance(call, dict) else None
    if not isinstance(result, dict) or result.get("exit_code") != 0:
        return False
    command_text = _tool_call_external_command_text(call)
    pattern = _command_example_regex(command)
    if not command_text or pattern is None:
        return False
    if re.search(r"\bcwd\s*=", command_text) or re.search(r"\bos\.chdir\s*\(", command_text):
        return False
    match = pattern.search(command_text)
    if not match:
        return False
    prefix = command_text[: match.start()]
    if re.search(r"[;&|]", prefix):
        return False
    # Command examples are user-facing invocation contracts. A preceding cd
    # wrapper can change where compiler defaults or relative outputs land, so
    # it is not evidence that the exact advertised invocation works.
    if re.search(r"(?:^|[;&|('\"]\s*)(?:cd|pushd)\s+\S+", prefix):
        return False
    if _COMMAND_EXAMPLE_SETUP_MUTATION_RE.search(prefix):
        return False
    try:
        command_tokens = shlex.split(command)
    except ValueError:
        command_tokens = command.split()
    first = command_tokens[0].casefold() if command_tokens else ""
    matched_text = command_text[match.start() : match.end()]
    if first in _COMMAND_EXAMPLE_OUTPUT_FLAG_TOOLS and "-o" not in command_tokens:
        if re.search(r"(?<![\w-])(?:-o|--out-dir)(?![\w-])", matched_text):
            return False
    return True


def _has_exact_command_example_evidence(evidence: object, session: object, command: str) -> bool:
    for call in _evidence_command_calls(evidence, session):
        if call.get("tool") not in {"run_command", "run_tests"}:
            continue
        if _command_example_call_matches(call, command):
            return True
    return False


def _evidence_tool_ids(text: object) -> list[int]:
    ids: list[int] = []
    for match in _TOOL_ID_RE.finditer(str(text or "")):
        try:
            tool_id = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if tool_id not in ids:
            ids.append(tool_id)
    return ids


def _check_evidence_refs(check: object) -> list[dict]:
    if not isinstance(check, dict):
        return []
    refs = _coerce_evidence_refs(check.get("evidence_refs") or check.get("evidence_ref"))
    for tool_id in _evidence_tool_ids(check.get("evidence")):
        ref = {"kind": "tool_call", "id": tool_id}
        if ref not in refs:
            refs.append(ref)
    return refs


def _evidence_command_calls(evidence: object, session: object) -> list[dict]:
    if isinstance(evidence, dict):
        refs = _check_evidence_refs(evidence)
    else:
        refs = [{"kind": "tool_call", "id": tool_id} for tool_id in _evidence_tool_ids(evidence)]
    calls: list[dict] = []
    seen: set[tuple[str, object]] = set()
    for ref in refs:
        ref_id = ref.get("id")
        if ref_id is None:
            continue
        kind = str(ref.get("kind") or "tool_call")
        key = (kind, ref_id)
        if key in seen:
            continue
        seen.add(key)
        if kind == "command_evidence":
            command_evidence = _command_evidence_by_id(session, ref_id)
            if command_evidence:
                calls.append(command_evidence_to_tool_call(command_evidence))
            continue
        if kind == "tool_call":
            call = _tool_call_by_id(session, ref_id)
            if call:
                calls.append(call)
    return calls


def _evidence_semantic_text(evidence: object) -> str:
    if isinstance(evidence, dict):
        return "\n".join(
            str(evidence.get(key) or "") for key in ("constraint", "evidence", "proof") if evidence.get(key)
        )
    return str(evidence or "")


def _evidence_ref_findings_for_checks(checks: list[dict], session: object) -> dict:
    if not isinstance(session, dict):
        return {"blocker": "", "invalid_refs": []}
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return {"blocker": "", "invalid_refs": []}
    missing: list[str] = []
    invalid: list[str] = []
    invalid_refs: list[dict] = []
    for check in verified_checks:
        refs = _check_evidence_refs(check)
        if not refs:
            missing.append(_clean_constraint_text(check.get("constraint"), limit=80) or "unnamed acceptance check")
            continue
        check_invalid: list[str] = []
        check_invalid_refs: list[dict] = []
        has_terminal_success_ref = False
        for ref in refs:
            kind = str(ref.get("kind") or "tool_call")
            ref_id = ref.get("id")
            if kind == "command_evidence":
                evidence = _command_evidence_by_id(session, ref_id)
                if not evidence:
                    check_invalid.append(f"command_evidence#{ref_id} missing")
                    check_invalid_refs.append({"kind": "command_evidence", "id": ref_id, "reason": "missing"})
                    continue
                if not evidence.get("terminal_success"):
                    evidence_ref = _command_evidence_ref_summary(evidence)
                    check_invalid.append(
                        "command_evidence#"
                        f"{ref_id} not terminal-success "
                        f"(status={evidence_ref.get('status')}, exit={evidence_ref.get('exit_code')}, "
                        f"timed_out={evidence_ref.get('timed_out')})"
                    )
                    check_invalid_refs.append(
                        {
                            "kind": "command_evidence",
                            "id": ref_id,
                            "reason": "not_terminal_success",
                            "status": evidence_ref.get("status"),
                            "exit_code": evidence_ref.get("exit_code"),
                            "timed_out": evidence_ref.get("timed_out"),
                        }
                    )
                    continue
                has_terminal_success_ref = True
                continue
            if kind != "tool_call":
                check_invalid.append(f"{kind}#{ref_id} unsupported")
                check_invalid_refs.append({"kind": kind, "id": ref_id, "reason": "unsupported_evidence_kind"})
                continue
            call = _any_tool_call_by_id(session, ref_id)
            if not call:
                check_invalid.append(f"tool_call#{ref_id} missing")
                check_invalid_refs.append({"kind": "tool_call", "id": ref_id, "reason": "missing"})
                continue
            if not tool_call_terminal_success(call):
                evidence = tool_call_evidence_ref(call)
                check_invalid.append(
                    "tool_call#"
                    f"{ref_id} not terminal-success "
                    f"(status={evidence.get('status')}, exit={evidence.get('exit_code')}, "
                    f"timed_out={evidence.get('timed_out')})"
                )
                check_invalid_refs.append(
                    {
                        "kind": "tool_call",
                        "id": ref_id,
                        "reason": "not_terminal_success",
                        "status": evidence.get("status"),
                        "exit_code": evidence.get("exit_code"),
                        "timed_out": evidence.get("timed_out"),
                    }
                )
                continue
            has_terminal_success_ref = True
        # Models sometimes cite the whole exploration chain in a verified
        # acceptance check. If the check also cites terminal-success evidence,
        # semantic blockers decide whether that evidence is sufficient; earlier
        # failed tool refs are noisy but should not force an extra model turn.
        # Missing or unsupported refs stay blocking because they indicate
        # malformed or hallucinated evidence, not merely historical exploration.
        if has_terminal_success_ref:
            for message, ref in zip(check_invalid, check_invalid_refs):
                if ref.get("reason") == "not_terminal_success":
                    continue
                invalid.append(message)
                invalid_refs.append(ref)
        else:
            invalid.extend(check_invalid)
            invalid_refs.extend(check_invalid_refs)
    if missing:
        return {
            "blocker": (
                "acceptance evidence refs missing: verified acceptance checks must cite "
                f"terminal tool evidence such as tool #N ({'; '.join(missing[:3])})"
            ),
            "invalid_refs": invalid_refs,
        }
    if invalid:
        return {"blocker": "acceptance evidence refs invalid: " + "; ".join(invalid[:3]), "invalid_refs": invalid_refs}
    return {"blocker": "", "invalid_refs": []}


def _evidence_ref_blocker_for_checks(checks: list[dict], session: object) -> str:
    return str(_evidence_ref_findings_for_checks(checks, session).get("blocker") or "")


def _has_post_write_grounding_evidence(evidence: object, session: object) -> bool:
    latest_write_id = _latest_completed_write_tool_id(session)
    if latest_write_id is None:
        return True
    refs = (
        _check_evidence_refs(evidence)
        if isinstance(evidence, dict)
        else [{"kind": "tool_call", "id": tool_id} for tool_id in _evidence_tool_ids(evidence)]
    )
    for ref in refs:
        kind = str(ref.get("kind") or "tool_call")
        ref_id = ref.get("id")
        if ref_id is None:
            continue
        if kind == "command_evidence":
            command_evidence = _command_evidence_by_id(session, ref_id)
            if not command_evidence:
                continue
            try:
                source_tool_call_id = int(command_evidence.get("source_tool_call_id") or 0)
            except (TypeError, ValueError):
                source_tool_call_id = 0
            if source_tool_call_id and source_tool_call_id <= latest_write_id:
                continue
            call = command_evidence_to_tool_call(command_evidence)
        elif kind == "tool_call":
            if ref_id <= latest_write_id:
                continue
            call = _tool_call_by_id(session, ref_id)
        else:
            continue
        if call and call.get("tool") in _GROUNDING_TOOLS:
            return True
    return False


def is_all_valid_answer_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _ALL_VALID_ANSWER_TASK_MARKERS):
        return False
    return any(marker in lowered for marker in ("all", "multiple", "one per line"))


def is_numeric_artifact_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if _NUMERIC_STRONG_TASK_RE.search(lowered):
        return True
    if _NUMERIC_FIT_RE.search(lowered):
        return any(
            marker in lowered
            for marker in (
                "curve",
                "data",
                "dataset",
                "model",
                "numeric",
                "parameter",
                "spectrum",
                "x0",
            )
        )
    if "regression" in lowered or "rank" in lowered or "ranking" in lowered:
        return any(marker in lowered for marker in ("metric", "score", "numeric", "dataset"))
    if "metric" in lowered or "metrics" in lowered:
        return any(marker in lowered for marker in ("compute", "numeric", "score", "dataset", "data file"))
    return False


def _has_completeness_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _COMPLETENESS_EVIDENCE_MARKERS)


def _has_all_valid_answer_grounding_evidence(evidence: object, session: object) -> bool:
    if not _has_completeness_marker(_evidence_semantic_text(evidence)):
        return False
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in _GROUNDING_TOOLS:
            continue
        if _has_completeness_marker(_tool_call_text(call)):
            return True
    return False


def _all_valid_answer_grounding_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_all_valid_answer_task(task_description):
        return ""
    completeness_checks = [
        check
        for check in checks
        if _has_completeness_marker(check.get("constraint"))
        or _has_completeness_marker(check.get("evidence"))
    ]
    if not completeness_checks:
        return (
            "all-valid answer completeness evidence missing: tasks asking for all, "
            "multiple, or one-per-line valid answers must cite independent enumeration "
            "or completeness proof before task_done=true"
        )
    for check in completeness_checks:
        if _has_all_valid_answer_grounding_evidence(check, session):
            return ""
    return (
        "all-valid answer completeness evidence ungrounded: completeness checks must "
        "cite a completed grounding tool whose output independently enumerates or "
        "proves the full answer set"
    )


def _edit_scope_grounding_blocker(
    constraints: list[str],
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if _latest_completed_write_tool_id(session) is None:
        return ""
    if not any(is_edit_scope_constraint(constraint) for constraint in constraints):
        return ""
    edit_scope_checks = [
        check
        for check in checks
        if is_edit_scope_constraint(check.get("constraint")) or is_edit_scope_constraint(check.get("evidence"))
    ]
    if not edit_scope_checks:
        return (
            "edit-scope acceptance evidence missing: constraints about only-allowed edits, "
            "specified replacements, or do-not-edit surfaces must be checked explicitly"
        )
    for check in edit_scope_checks:
        if _has_post_write_grounding_evidence(check, session):
            continue
        return (
            "edit-scope acceptance evidence ungrounded: constraints about only-allowed edits, "
            "specified replacements, or do-not-edit surfaces must cite a completed validator, "
            "diff, or final inspection tool after the latest write; write history alone is not enough"
        )
    return ""


def _has_numeric_check_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _NUMERIC_CHECK_MARKERS)


def _has_numeric_independence_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _NUMERIC_INDEPENDENCE_MARKERS)


def _has_numeric_artifact_quality_evidence(evidence: object, session: object) -> bool:
    semantic_text = _evidence_semantic_text(evidence)
    if not (_has_numeric_check_marker(semantic_text) and _has_numeric_independence_marker(semantic_text)):
        return False
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in _GROUNDING_TOOLS:
            continue
        tool_text = _tool_call_text(call)
        if _has_numeric_check_marker(tool_text) and _has_numeric_independence_marker(tool_text):
            return True
    return False


def is_query_only_hidden_model_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not (_QUERY_ONLY_FORWARD_RE.search(lowered) and _QUERY_ONLY_ACCESS_RE.search(lowered)):
        return False
    if not any(marker in lowered for marker in _QUERY_ONLY_UNKNOWN_MARKERS):
        return False
    return any(marker in lowered for marker in _QUERY_ONLY_HIDDEN_MODEL_MARKERS)


def _write_source_fragments(call: dict) -> list[tuple[str, str]]:
    parameters = call.get("parameters")
    if not isinstance(parameters, dict):
        return []
    path = str(parameters.get("path") or "")
    fragments: list[tuple[str, str]] = []
    for key in ("content", "new", "replacement"):
        value = parameters.get(key)
        if isinstance(value, str) and value:
            fragments.append((path, value))
    edits = parameters.get("edits")
    if isinstance(edits, list):
        for index, edit in enumerate(edits):
            if not isinstance(edit, dict):
                continue
            value = edit.get("new") or edit.get("replacement")
            if isinstance(value, str) and value:
                fragments.append((path, value))
    return fragments


def _forward_module_aliases(content: str) -> list[str]:
    aliases: list[str] = []
    for match in _QUERY_ONLY_FORWARD_IMPORT_ALIAS_RE.finditer(content):
        alias = match.group(1) or "forward"
        if alias not in aliases:
            aliases.append(alias)
    for match in _QUERY_ONLY_FORWARD_DYNAMIC_IMPORT_ALIAS_RE.finditer(content):
        alias = match.group(1)
        if alias not in aliases:
            aliases.append(alias)
    return aliases


def _query_only_source_forbidden_match(content: str) -> str:
    for pattern in _QUERY_ONLY_FORBIDDEN_SOURCE_PATTERNS:
        match = pattern.search(content)
        if match:
            return match.group(0)
    if _QUERY_ONLY_FORWARD_STAR_IMPORT_RE.search(content) and _QUERY_ONLY_SECRET_RE.search(content):
        return "from forward import * with direct hidden weight name"
    match = _QUERY_ONLY_INLINE_DYNAMIC_IMPORT_SECRET_RE.search(content)
    if match:
        return match.group(0)
    for alias in _forward_module_aliases(content):
        attr_pattern = re.compile(rf"\b{re.escape(alias)}\s*\.\s*(?:A1|A2|b1|b2)\b")
        match = attr_pattern.search(content)
        if match:
            return match.group(0)
        dict_pattern = re.compile(
            rf"\b{re.escape(alias)}\s*\.\s*__dict__\s*\[\s*['\"](?:A1|A2|b1|b2)['\"]\s*\]"
        )
        match = dict_pattern.search(content)
        if match:
            return match.group(0)
        vars_pattern = re.compile(
            rf"\bvars\s*\(\s*{re.escape(alias)}\s*\)\s*\[\s*['\"](?:A1|A2|b1|b2)['\"]\s*\]"
        )
        match = vars_pattern.search(content)
        if match:
            return match.group(0)
        dynamic_pattern = re.compile(
            rf"\b(?:getattr|hasattr)\s*\(\s*{re.escape(alias)}\s*,\s*['\"](?:A1|A2|b1|b2)['\"]"
        )
        match = dynamic_pattern.search(content)
        if match:
            return match.group(0)
    return ""


def _completed_write_source_violations(session: object) -> list[str]:
    violations: list[str] = []
    for call in _completed_tool_calls(session):
        if call.get("tool") not in _WRITE_TOOLS:
            continue
        for path, content in _write_source_fragments(call):
            if not path.endswith(".py") or not content:
                continue
            match_text = _query_only_source_forbidden_match(content)
            if match_text:
                violations.append(f"tool #{call.get('id')} {path}: {match_text}")
    return violations


def _has_query_only_generalization_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _QUERY_ONLY_GENERALIZATION_MARKERS)


def _has_query_only_generalization_success(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _QUERY_ONLY_GENERALIZATION_SUCCESS_MARKERS) or bool(
        _QUERY_ONLY_ALL_MATCHED_TRUE_RE.search(str(text or ""))
    )


def _has_failed_generalization_clause(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _QUERY_ONLY_GENERALIZATION_FAILURE_MARKERS)


def _has_passing_query_only_generalization_clause(text: object) -> bool:
    clauses = re.split(r"[\n\r;]+|(?<=[.!?])\s+", str(text or ""))
    for clause in clauses:
        if not _has_query_only_generalization_marker(clause):
            continue
        if not _has_query_only_generalization_success(clause):
            continue
        if _has_failed_generalization_clause(clause):
            continue
        return True
    return False


def _has_query_only_generalization_evidence(evidence: object, session: object) -> bool:
    if not _has_passing_query_only_generalization_clause(_evidence_semantic_text(evidence)):
        return False
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in _GROUNDING_TOOLS:
            continue
        tool_text = _tool_call_text(call)
        if _has_passing_query_only_generalization_clause(tool_text):
            return True
    return False


def _query_only_hidden_model_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_query_only_hidden_model_task(task_description):
        return ""
    source_violations = _completed_write_source_violations(session)
    if source_violations:
        return (
            "query-only hidden-model source violation: tasks that expose only forward(x) "
            "query access must not finish with generated source that reads visible model "
            f"internals ({'; '.join(source_violations[:3])})"
        )
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if not verified_checks:
        return (
            "query-only hidden-model generalization evidence missing: black-box model "
            "extraction tasks must cite synthetic, randomized, or holdout validation before task_done=true"
        )
    if any(_has_query_only_generalization_evidence(check, session) for check in verified_checks):
        return ""
    return (
        "query-only hidden-model generalization evidence ungrounded: visible fixture checks "
        "against exposed local weights are not enough; cite a completed tool with synthetic, "
        "randomized, or holdout validation that passed"
    )


def is_model_inference_output_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _MODEL_INFERENCE_SOURCE_MARKERS):
        return False
    if "weights" in lowered and not any(
        marker in lowered
        for marker in (
            ".bpe",
            ".ckpt",
            "checkpoint",
            "gpt",
            "llm",
            "model",
            "model.bin",
            "tokenizer",
            "transformer",
            "vocab.bpe",
        )
    ):
        return False
    if not any(marker in lowered for marker in _MODEL_INFERENCE_ACTION_MARKERS):
        return False
    if not any(marker in lowered for marker in _MODEL_INFERENCE_OUTPUT_MARKERS):
        return False
    return True


def _has_model_inference_check_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _MODEL_INFERENCE_CHECK_MARKERS)


def _model_inference_clause_has_failed_ratio(text: str) -> bool:
    for match in _MODEL_INFERENCE_RATIO_RE.finditer(text):
        try:
            numerator = int(match.group(1))
            denominator = int(match.group(2))
        except (TypeError, ValueError):
            continue
        if denominator > 0 and numerator < denominator:
            return True
    return False


def _has_model_inference_oracle_success_clause(text: object) -> bool:
    clauses = re.split(r"[\n\r;]+|(?<=[.!?])\s+", str(text or ""))
    for clause in clauses:
        lowered = clause.casefold()
        if not any(marker in lowered for marker in _MODEL_INFERENCE_ORACLE_MARKERS):
            continue
        candidate_equals = _MODEL_INFERENCE_CANDIDATE_EQUALS_RE.search(lowered)
        if candidate_equals:
            value = str(candidate_equals.group("value") or "").casefold()
            if value and value not in {"1", "pass", "passed", "true", "yes"}:
                continue
            if not value and "candidate_equals_reference true" not in lowered:
                continue
        if _MODEL_INFERENCE_ORACLE_FALSE_VALUE_RE.search(lowered):
            continue
        has_success_marker = any(marker in lowered for marker in _MODEL_INFERENCE_ORACLE_SUCCESS_MARKERS)
        has_zero_negative_count = bool(_MODEL_INFERENCE_ZERO_NEGATIVE_COUNT_RE.search(lowered))
        if not has_success_marker and not has_zero_negative_count:
            continue
        failure_text = _MODEL_INFERENCE_ZERO_NEGATIVE_COUNT_RE.sub("", lowered)
        if any(marker in failure_text for marker in _MODEL_INFERENCE_ORACLE_FAILURE_MARKERS):
            continue
        if _model_inference_clause_has_failed_ratio(lowered):
            continue
        return True
    return False


def _model_inference_reference_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").casefold()
    if not normalized:
        return False
    basename = normalized.rsplit("/", 1)[-1]
    if "/tests/" in normalized or normalized.startswith("tests/"):
        return True
    return any(marker in basename for marker in ("expected", "golden", "oracle", "reference", "truth"))


def _model_inference_candidate_source_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").casefold()
    if not normalized:
        return False
    return not _model_inference_reference_path(normalized)


def _has_model_inference_self_derived_path_operation(text: object) -> bool:
    value = str(text or "")
    for pattern in (
        _MODEL_INFERENCE_OPEN_READ_WRITE_RE,
        _MODEL_INFERENCE_COPY_TO_REF_RE,
        _MODEL_INFERENCE_CAT_TO_REF_RE,
    ):
        for match in pattern.finditer(value):
            src = match.group("src")
            if _model_inference_candidate_source_path(src):
                return True
    return False


def _has_model_inference_self_derived_oracle(text: object) -> bool:
    value = str(text or "")
    if not value.strip():
        return False
    if any(pattern.search(value) for pattern in _MODEL_INFERENCE_SELF_DERIVED_ORACLE_PATTERNS):
        return True
    return _has_model_inference_self_derived_path_operation(value)


def _normalize_model_inference_path(path: object) -> str:
    return str(path or "").strip().strip("'\"").replace("\\", "/").casefold()


def _model_inference_task_reference_copy_allowance(text: object) -> tuple[set[str], list[tuple[int, int]]]:
    value = str(text or "")
    destinations: set[str] = set()
    spans: list[tuple[int, int]] = []
    for pattern in _MODEL_INFERENCE_TASK_REFERENCE_COPY_RE:
        for match in pattern.finditer(value):
            src = match.group("src") or ""
            dst = match.group("dst") or ""
            if not src or not dst:
                continue
            if not _model_inference_reference_path(src):
                continue
            destinations.add(_normalize_model_inference_path(dst))
            spans.append(match.span())
    return destinations, spans


def _without_spans(value: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return value
    chars = list(value)
    for start, end in spans:
        for index in range(max(0, start), min(len(chars), end)):
            chars[index] = " "
    return "".join(chars)


def _model_inference_generated_oracle_targets(text: object) -> list[str]:
    value = str(text or "")
    targets: list[str] = []
    for pattern in _MODEL_INFERENCE_GENERATED_ORACLE_TARGET_RE:
        for match in pattern.finditer(value):
            path = _normalize_model_inference_path(match.group("path"))
            if path:
                targets.append(path)
    return targets


def _has_model_inference_ephemeral_oracle_source(text: object) -> bool:
    value = str(text or "")
    if not value.strip():
        return False
    allowed_destinations, allowed_spans = _model_inference_task_reference_copy_allowance(value)
    for match in _MODEL_INFERENCE_EPHEMERAL_ORACLE_PATH_RE.finditer(value):
        if _normalize_model_inference_path(match.group(0)) not in allowed_destinations:
            return True
    scan_value = _without_spans(value, allowed_spans)
    if _model_inference_generated_oracle_targets(scan_value):
        return True
    return False


def _model_inference_generated_oracle_blocker_text() -> str:
    return (
        "model inference oracle provenance ungrounded: an oracle/reference source "
        "generated in the current work session or under /tmp is not independent "
        "model-output evidence; cite a task-provided, external, golden, or hidden "
        "verifier-derived reference/expected-continuation check"
    )


def _model_inference_self_derived_oracle_blocker(evidence: object, session: object) -> str:
    semantic_text = _evidence_semantic_text(evidence)
    if not _has_model_inference_oracle_success_clause(semantic_text):
        return ""
    if _has_model_inference_ephemeral_oracle_source(semantic_text):
        return _model_inference_generated_oracle_blocker_text()
    if _has_model_inference_self_derived_oracle(semantic_text):
        return (
            "model inference oracle provenance ungrounded: a reference/oracle built from "
            "the current candidate implementation or same source is not independent; cite "
            "a completed tool using a task-provided, external, golden, or independently "
            "derived reference/expected-continuation check"
        )
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in {"run_command", "run_tests"}:
            continue
        result_text = _tool_call_result_text(call)
        if not _has_model_inference_oracle_success_clause(result_text):
            continue
        if _has_model_inference_ephemeral_oracle_source(_tool_call_text(call)):
            return _model_inference_generated_oracle_blocker_text()
        if _has_model_inference_self_derived_oracle(_tool_call_text(call)):
            return (
                "model inference oracle provenance ungrounded: a reference/oracle built from "
                "the current candidate implementation or same source is not independent; cite "
                "a completed tool using a task-provided, external, golden, or independently "
                "derived reference/expected-continuation check"
            )
    return ""


def _has_model_inference_output_quality_evidence(evidence: object, session: object) -> bool:
    semantic_text = _evidence_semantic_text(evidence)
    if not _has_model_inference_oracle_success_clause(semantic_text):
        return False
    if _has_model_inference_ephemeral_oracle_source(semantic_text):
        return False
    if _has_model_inference_self_derived_oracle(semantic_text):
        return False
    for call in _evidence_command_calls(evidence, session):
        if not call or call.get("tool") not in {"run_command", "run_tests"}:
            continue
        if _has_model_inference_ephemeral_oracle_source(_tool_call_text(call)):
            continue
        if _has_model_inference_self_derived_oracle(_tool_call_text(call)):
            continue
        if _has_model_inference_oracle_success_clause(_tool_call_result_text(call)):
            return True
    return False


def _model_inference_output_quality_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_model_inference_output_task(task_description):
        return ""
    inference_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
        and (
            _has_model_inference_check_marker(check.get("constraint"))
            or _has_model_inference_check_marker(check.get("evidence"))
        )
    ]
    if not inference_checks:
        return (
            "model inference output quality evidence missing: checkpoint, tokenizer, "
            "or model-sampling tasks must cite reference, golden, argmax/top-1, "
            "logit, token-id, or expected-continuation validation before task_done=true"
        )
    for check in inference_checks:
        if _has_model_inference_output_quality_evidence(check, session):
            return ""
    for check in inference_checks:
        blocker = _model_inference_self_derived_oracle_blocker(check, session)
        if blocker:
            return blocker
    return (
        "model inference output quality evidence ungrounded: compile success, "
        "byte-size checks, CLI shape, and token-count smoke output are not enough; "
        "cite a completed run_command or run_tests tool whose result proves reference, "
        "golden, argmax/top-1, logit, token-id, or expected-continuation equivalence"
    )


def _command_requirement_terms(command: str, backtick_values: list[str]) -> list[str]:
    terms: list[str] = []
    if command:
        terms.append(command)
    for value in backtick_values:
        try:
            tokens = shlex.split(value)
        except ValueError:
            tokens = value.split()
        if not tokens:
            continue
        if not command and tokens[0] and not tokens[0].startswith("-"):
            command = tokens[0]
            if command not in terms:
                terms.insert(0, command)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not token.startswith("-"):
                index += 1
                continue
            if "=" in token:
                term = token
            elif index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                term = f"{token} {tokens[index + 1]}"
                index += 1
            else:
                term = token
            if term not in terms:
                terms.append(term)
            index += 1
    return terms


def external_tool_ground_truth_requirements(text: object) -> list[dict[str, object]]:
    requirements: list[dict[str, object]] = []
    for sentence in _constraint_sentences(str(text or "")):
        lowered = sentence.casefold()
        if not _GROUND_TRUTH_RE.search(lowered):
            continue
        if not any(marker in lowered for marker in _EXTERNAL_TOOL_REQUIREMENT_MARKERS):
            continue
        command = ""
        match = _OUTPUT_OF_TOOL_RE.search(sentence)
        if match:
            command = match.group(1)
        backtick_values = [_clean_constraint_text(value, limit=120) for value in _BACKTICK_TEXT_RE.findall(sentence)]
        if not command:
            for value in backtick_values:
                try:
                    tokens = shlex.split(value)
                except ValueError:
                    tokens = value.split()
                if tokens and _WORDISH_COMMAND_RE.match(tokens[0]) and not tokens[0].startswith("-"):
                    command = tokens[0]
                    break
        if not command:
            continue
        requirements.append(
            {
                "command": command,
                "required_terms": _command_requirement_terms(command, backtick_values),
                "sentence": sentence,
            }
        )
    return requirements


def _has_external_tool_grounding_evidence(evidence: object, session: object, requirement: dict[str, object]) -> bool:
    command = str(requirement.get("command") or "").casefold()
    required_terms = [_normalized_command_text(term) for term in requirement.get("required_terms") or []]
    if not command:
        return True
    for call in _evidence_command_calls(evidence, session):
        if call.get("tool") not in {"run_command", "run_tests"}:
            continue
        command_text = _tool_call_external_command_text(call)
        if all(_external_command_text_contains_term(command_text, term) for term in required_terms):
            return True
    return False


def _external_tool_ground_truth_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    requirements = external_tool_ground_truth_requirements(task_description)
    if not requirements:
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    for requirement in requirements:
        command = requirement.get("command")
        matching_checks = [
            check
            for check in verified_checks
            if str(command or "").casefold()
            in f"{check.get('constraint') or ''}\n{check.get('evidence') or ''}".casefold()
        ]
        if not matching_checks:
            return (
                "external ground-truth tool evidence missing: tasks that name an exact "
                "ground-truth command/tool must cite that exact command and flags before task_done=true"
            )
        if not any(_has_external_tool_grounding_evidence(check, session, requirement) for check in matching_checks):
            return (
                "external ground-truth tool evidence ungrounded: exact command/tool constraints "
                "must cite a completed run_command or run_tests tool whose command/output contains "
                "the named ground-truth command and required flags"
            )
    return ""


def _exact_command_example_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    requirements = exact_command_example_requirements(task_description)
    if not requirements:
        return ""
    verified_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    for requirement in requirements:
        command = str(requirement.get("command") or "")
        if not verified_checks:
            return (
                "exact command example evidence missing: tasks that state a command can be run "
                "must cite that exact command shape before task_done=true"
            )
        if not any(_has_exact_command_example_evidence(check, session, command) for check in verified_checks):
            return (
                "exact command example evidence ungrounded: command-example constraints must "
                "cite a completed run_command or run_tests tool that runs the advertised command "
                "shape without a preceding cwd-changing cd wrapper"
            )
    return ""


def _numeric_artifact_quality_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_numeric_artifact_task(task_description):
        return ""
    numeric_checks = [
        check
        for check in checks
        if str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
        and (_has_numeric_check_marker(check.get("constraint")) or _has_numeric_check_marker(check.get("evidence")))
    ]
    if not numeric_checks:
        return (
            "numeric artifact quality evidence missing: fitting, optimization, ranking, "
            "scientific, or metric tasks must cite an independent numeric validation "
            "before task_done=true"
        )
    for check in numeric_checks:
        if _has_numeric_artifact_quality_evidence(check, session):
            return ""
    return (
        "numeric artifact quality evidence ungrounded: numeric checks must cite a completed "
        "grounding tool whose output contains an independent cross-check, alternative method, "
        "recomputation, holdout, bootstrap, or sensitivity/stability validation; schema, "
        "finite-number, single-fit residual, or readback-only evidence is not enough"
    )


def acceptance_finish_blocker(
    task_description: object,
    action: object,
    *,
    session: object = None,
    include_runtime_component_gate: bool = True,
) -> str:
    action = action if isinstance(action, dict) else {}
    if not action.get("task_done"):
        return ""
    checks = coerce_acceptance_checks(action.get("acceptance_checks"))
    all_valid_answer_blocker = _all_valid_answer_grounding_blocker(task_description, checks, session)
    if all_valid_answer_blocker:
        return all_valid_answer_blocker
    external_tool_blocker = _external_tool_ground_truth_blocker(task_description, checks, session)
    if external_tool_blocker:
        return external_tool_blocker
    exact_command_blocker = _exact_command_example_blocker(task_description, checks, session)
    if exact_command_blocker:
        return exact_command_blocker
    implementation_contract_blocker = _implementation_contract_source_blocker(task_description, checks, session)
    if implementation_contract_blocker:
        return implementation_contract_blocker
    runtime_artifact_final_blocker = _runtime_artifact_final_state_blocker(task_description, checks, session)
    if runtime_artifact_final_blocker:
        return runtime_artifact_final_blocker
    runtime_visual_artifact_blocker = _runtime_visual_artifact_quality_blocker(task_description, checks, session)
    if runtime_visual_artifact_blocker:
        return runtime_visual_artifact_blocker
    runtime_artifact_blocker = _runtime_artifact_freshness_blocker(task_description, checks, session)
    if runtime_artifact_blocker:
        return runtime_artifact_blocker
    if include_runtime_component_gate:
        runtime_component_blocker = _runtime_component_behavior_blocker(task_description, checks, session)
        if runtime_component_blocker:
            return runtime_component_blocker
    long_dependency_blocker = _long_dependency_build_artifact_blocker(task_description, checks, session)
    if long_dependency_blocker:
        return long_dependency_blocker
    stateful_output_blocker = _stateful_output_semantic_contrast_blocker(task_description, checks, session)
    if stateful_output_blocker:
        return stateful_output_blocker
    query_only_blocker = _query_only_hidden_model_blocker(task_description, checks, session)
    if query_only_blocker:
        return query_only_blocker
    model_inference_blocker = _model_inference_output_quality_blocker(task_description, checks, session)
    if model_inference_blocker:
        return model_inference_blocker
    numeric_artifact_blocker = _numeric_artifact_quality_blocker(task_description, checks, session)
    if numeric_artifact_blocker:
        return numeric_artifact_blocker
    constraints = extract_acceptance_constraints(task_description)
    if not constraints:
        return ""
    verified = [
        check
        for check in checks
        if check.get("constraint")
        and check.get("evidence")
        and str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if len(verified) >= len(constraints):
        edit_scope_blocker = _edit_scope_grounding_blocker(constraints, verified, session)
        if edit_scope_blocker:
            return edit_scope_blocker
        return ""
    return (
        "acceptance constraints unchecked: finish with task_done=true must include "
        "acceptance_checks with verified status and direct evidence for every stated constraint"
    )


def finish_blocker_code(blocker: object) -> str:
    text = str(blocker or "").casefold()
    if "pending approval" in text:
        return "pending_approval"
    if "unverified source-edit verification" in text:
        return "unverified_source_edit"
    if "same-surface audit" in text:
        return "same_surface_audit_required"
    if "acceptance evidence refs missing" in text:
        return "acceptance_evidence_refs_missing"
    if "acceptance evidence refs invalid" in text:
        return "acceptance_evidence_refs_invalid"
    if "acceptance constraints unchecked" in text:
        return "acceptance_constraints_unchecked"
    if "long dependency/toolchain final artifact evidence" in text:
        return "long_dependency_final_artifact_evidence"
    if "runtime final verifier artifact evidence" in text:
        return "runtime_final_verifier_artifact_evidence"
    if "runtime artifact freshness unchecked" in text:
        return "runtime_artifact_freshness_unchecked"
    if "runtime visual artifact quality evidence" in text:
        return "runtime_visual_artifact_quality_evidence"
    if "runtime component behavior evidence" in text:
        return "runtime_component_behavior_evidence"
    if "numeric artifact quality evidence" in text:
        return "numeric_artifact_quality_evidence"
    if "edit-scope acceptance evidence" in text:
        return "edit_scope_acceptance_evidence"
    if "all-valid answer completeness evidence" in text:
        return "all_valid_answer_completeness_evidence"
    if "external ground-truth" in text:
        return "external_ground_truth_evidence"
    if "exact command" in text:
        return "exact_command_evidence"
    if "query-only hidden-model" in text:
        return "query_only_hidden_model_evidence"
    if "model inference output quality evidence" in text:
        return "model_inference_output_quality_evidence"
    if "model inference oracle provenance" in text:
        return "model_inference_oracle_provenance"
    return "finish_blocked"


def finish_continuation_prompt(blockers: list[object]) -> str:
    reasons = [str(blocker or "").strip() for blocker in blockers if str(blocker or "").strip()]
    if not reasons:
        return ""
    bullets = "\n".join(f"- {reason}" for reason in reasons[:8])
    return (
        "Finish was blocked by the deterministic done gate. Continue the same task; "
        "do not mark task_done=true until each blocker is repaired with terminal tool evidence.\n"
        f"{bullets}\n"
        "Next action: run the smallest read, diff, verifier, or artifact-smoke command that directly proves "
        "the missing acceptance item, then cite its tool id in acceptance_checks evidence_refs or evidence text."
    )


def runtime_component_finish_gate_decision(
    task_description: object,
    action: object,
    *,
    session: object = None,
) -> dict:
    action = action if isinstance(action, dict) else {}
    if not action.get("task_done"):
        return {
            "decision": "allow_complete",
            "reason": "",
            "blockers": [],
            "invalid_evidence_refs": [],
            "continuation_prompt": "",
        }
    checks = coerce_acceptance_checks(action.get("acceptance_checks"))
    blocker = _runtime_component_behavior_blocker(task_description, checks, session)
    if not blocker:
        return {
            "decision": "allow_complete",
            "reason": "",
            "blockers": [],
            "invalid_evidence_refs": [],
            "continuation_prompt": "",
        }
    blockers = [blocker]
    return {
        "decision": "block_continue",
        "reason": blocker,
        "blockers": [
            {
                "code": finish_blocker_code(blocker),
                "message": blocker,
            }
        ],
        "invalid_evidence_refs": [],
        "continuation_prompt": finish_continuation_prompt(blockers),
    }


def acceptance_done_gate_decision(
    task_description: object,
    action: object,
    *,
    session: object = None,
) -> dict:
    action = action if isinstance(action, dict) else {}
    if not action.get("task_done"):
        return {
            "decision": "allow_complete",
            "reason": "",
            "blockers": [],
            "invalid_evidence_refs": [],
            "continuation_prompt": "",
        }
    blockers: list[str] = []
    runtime_component_gate = runtime_component_finish_gate_decision(task_description, action, session=session)
    if runtime_component_gate.get("decision") != "allow_complete":
        blockers.extend(
            blocker.get("message")
            for blocker in runtime_component_gate.get("blockers") or []
            if isinstance(blocker, dict) and blocker.get("message")
        )
    acceptance_blocker = acceptance_finish_blocker(
        task_description,
        action,
        session=session,
        include_runtime_component_gate=False,
    )
    if acceptance_blocker:
        blockers.append(acceptance_blocker)
    checks = coerce_acceptance_checks(action.get("acceptance_checks"))
    evidence_ref_findings = _evidence_ref_findings_for_checks(checks, session)
    evidence_ref_blocker = str(evidence_ref_findings.get("blocker") or "")
    if evidence_ref_blocker:
        blockers.append(evidence_ref_blocker)
    if not blockers:
        return {
            "decision": "allow_complete",
            "reason": "",
            "blockers": [],
            "invalid_evidence_refs": [],
            "continuation_prompt": "",
        }
    return {
        "decision": "block_continue",
        "reason": blockers[0],
        "blockers": [
            {
                "code": finish_blocker_code(blocker),
                "message": blocker,
            }
            for blocker in blockers
        ],
        "invalid_evidence_refs": [dict(item) for item in evidence_ref_findings.get("invalid_refs") or []],
        "continuation_prompt": finish_continuation_prompt(blockers),
    }
