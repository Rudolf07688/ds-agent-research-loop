# Phase 0 Research: Memory-Regime Abstraction & Decision Provenance

All Technical Context items are known (the stack and persistence are inherited from 003/004). The
open decisions are *design* choices for the verification layer. Each is resolved below.

## Decision 1 — Verified replay via deterministic rebuild + hash equality

**Decision**: `provenance.replay_view(record, history_up_to)` reconstructs a decision's memory view by
calling the unchanged `memory.build_view` with the recorded regime, `k`, and (for compacted) the
artifact that was current at that iteration, using only persisted history strictly *before* that
decision; it asserts the rebuilt `MemoryView.content_hash` equals the stored
`ExperimentRecord.memory_view_ref` (and the stored `MemoryView.content_hash`). `verify_cell(cell_id)`
runs this for every recorded decision and returns a `ReplayResult`.

**Rationale**: `build_view` is already pure and deterministic (`content_hash` is SHA-256 over
`rendered_text`). Reusing the *same* constructor for replay guarantees that "what we rebuild" and
"what was shown" are produced by identical code — the only way the hashes can match. No LLM calls are
needed because the view is a function of persisted records/artifacts (Principle IX). A mismatch
fails loudly and names the offending iteration (Principle X).

**Alternatives considered**:
- *Store-only, no replay verification* (the rejected clarification option) — persists the view but
  never proves it is reproducible; weaker Principle IX guarantee.
- *Re-run the loop to reproduce views* — would require LLM calls and re-training; non-deterministic
  and expensive. Rejected.
- *Diff rendered_text directly instead of hashes* — works but the content hash already is the
  canonical equality token used by `memory_view_ref`; comparing hashes keeps one source of truth and
  makes corruption detection a single comparison.

## Decision 2 — Config fingerprint excludes regime + memory, rides in `repro` JSONB

**Decision**: `provenance.config_fingerprint(cell, descriptor)` returns a stable SHA-256 over a
canonicalized dict of the held-fixed factors — prompt/schema version, action space, model allowlist,
budget (`N`)/patience (`k_patience`), `split_ref` + benchmark version, scoring (primary metric +
direction), and seed — **excluding** `regime`, `k` (the memory-tail size), and any memory content.
It is stamped into `ExperimentCell.repro["config_fingerprint"]` at run time. No schema change (repro
is already `JSONB`).

**Rationale**: The audit needs a single comparable token for "everything except memory." The existing
`repro` stamp already carries commit/settings/benchmark_version/split_ref; adding a derived
fingerprint there avoids a migration (Principle IV stays satisfied) and keeps the value persisted and
exportable. Canonicalization (sorted keys, normalized types) makes the digest order-independent and
reproducible.

**Alternatives considered**:
- *New `config_fingerprints` table + migration* — unnecessary; the value is small, derived, and
  cell-scoped. Rejected to honor Principle I (no schema churn for a derivable field).
- *Compare raw factor dicts instead of a hash* — the audit report does surface the differing factor,
  but a single fingerprint gives a cheap equality gate and a stable attribution token for downstream
  results. We keep both: hash for the gate, factor dict for the human-readable diff.

**Boundary care**: `k` is part of the *memory regime configuration*, not a held-fixed factor, so it is
**excluded** from the fingerprint — two cells differing only in `k` are still a valid memory-only
comparison. The audit reports `k`/regime as the intended difference, never as contamination.

## Decision 3 — Cross-regime audit: same-(member, seed) gate, fingerprint equality, memory diff

**Decision**: `provenance.audit_regimes(cell_a, cell_b)` (1) rejects the pair unless they share the
same `(dataset_id/member, seed)` (else "not a memory-only comparison"); (2) asserts equal
`config_fingerprint`, failing loudly and naming the first differing held-fixed factor on mismatch
(contamination); (3) on success, reports the regimes/`k` as the differing dimension and exposes the
per-iteration `MemoryView`s of both cells for side-by-side inspection. Returns an `AuditResult`.

**Rationale**: This operationalizes Principle XIII's "memory is the sole intervention" as a checkable
property rather than an assumption, which is exactly what the 007 study will rely on.

**Alternatives considered**:
- *Audit across any two cells* — meaningless across different members/seeds; the gate prevents a
  false "clean comparison" verdict. Rejected.
- *Audit only final scores* — would miss per-decision contamination; the per-iteration view exposure
  is what makes the comparison auditable. Rejected.

## Decision 4 — Regime selection as scalar `Settings` config; unknown rejected at startup

**Decision**: Add a scalar `regime` (and reuse `k`) to `Settings` for the single-run `ds-agent-loop`
path; parse/validate against the `MemoryRegime` enum at startup (pydantic validator) so an unknown or
malformed value fails fast before any run. The sweep path keeps its existing `regimes` list. The loop
body keeps its single `build_view` seam — no regime branching beyond it (FR-001).

**Rationale**: Regime must be "configuration, not a fork" (Principle XIII). A typed enum field with a
startup validator gives FR-002's fail-fast behavior using the existing pydantic-settings machinery
(Principle VIII), with no new config system.

**Alternatives considered**:
- *Silent default to recent_only on bad input* — violates FR-002 (no silent default). Rejected.
- *CLI flag only* — `Settings` is the single source of truth (Principle VIII); a flag would still map
  into it. We expose it through `Settings` and let the entrypoint pass it.

## Decision 5 — Re-key the run path to 004 members; one regime/`k` per cell

**Decision**: The single-run path resolves the member descriptor + frozen split via 004's
`load_member` (content-hash asserted), removing the on-disk `frozen_split` fallback from the *run*
path (kept only for offline unit tests). On resume of an existing `cell_id`, if the requested
regime/`k` differ from the persisted cell's, fail loudly (FR-012) — a cell is one regime for life.

**Rationale**: 004 made datasets/splits/budgets/action-spaces fixed and member-addressable; binding
the memory abstraction to `load_member` is what makes provenance keyed to `(member, seed, regime,
iteration)` and guarantees the held-fixed factors are exactly the benchmark's. `cell_id_for` already
encodes regime/`k`, so a mismatch is structurally a different cell; the explicit guard turns a silent
divergence into a loud error (Principle X).

**Alternatives considered**:
- *Allow regime change mid-cell* — destroys the controlled variable; rejected by FR-012.
- *Keep the on-disk split fallback in the run path* — risks a run using a non-materialized split,
  breaking byte-identity guarantees from 004. Restricted to tests only.

## Decision 6 — Compacted regime consumes the existing 003 `compaction.py` artifact opaquely

**Decision**: Per the 2026-06-13 clarification, the compacted+recent regime keeps consuming whatever
artifact `store.latest_artifact(cell_id)` returns (produced by the existing 003 `compaction.py`
path); 005 treats it as an opaque input and adds no new LLM job (FR-016). The empty-artifact
fallback (behaves as recent-only) is unchanged and remains replayable.

**Rationale**: Keeps the compacted regime genuinely runnable/auditable now while leaving the typed
belief-schema operator and outer compaction loop to feature 006, which can swap the producer in
without touching the 005 memory seam.

**Alternatives considered**: fixture-only or deterministic-fallback-only artifacts (the other two
clarification options) — both leave the compacted regime under-exercised against real artifacts;
rejected in favor of reusing the working 003 producer.

## Resolved unknowns

No `NEEDS CLARIFICATION` markers remain. Defaults deferred from `/speckit-clarify` are fixed here:
the single-run **default regime** is `recent_only` and the **default `k`** is the existing
`Settings` value; the **all-raw context-token limit** uses the existing `context_token_limit`
plumbed into `run_cell` (derived from the configured model's context window), not a new constant.
