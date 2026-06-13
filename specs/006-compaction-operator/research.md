# Phase 0 Research: Directional Research Memory Compaction Operator

All Technical Context items were resolvable from the existing 003/005 codebase and the constitution;
no `NEEDS CLARIFICATION` remained. The decisions below pin the harden+verify approach.

## Decision 1 — Reuse the 003 producer; do not rewrite

- **Decision**: Keep `compaction.py` (`should_compact`, `select_source`, `compact`) and the
  `DirectionalMemory` belief schema (`prompts.py`) as the operator. 006 hardens their invariants and
  adds verification; it does not redefine the schema or replace the producer.
- **Rationale**: The schema already captures Principle XII's required dimensions
  (`confirmed_findings`/`failed_directions`/`promising_directions`/`unresolved_questions` +
  `best_known_configs`/`next_step_recommendation`/`confidence`/`rationale`) with `extra="forbid"`.
  The outer loop already fires at cadence and persists via `save_artifact`. Rewriting would risk the
  005 guarantees for no benefit.
- **Alternatives considered**: New artifact schema (rejected — already satisfies XII and is consumed
  by 005's `build_view._render_artifact`); new operator module (rejected — duplicates existing code).

## Decision 2 — Record the cadence with each artifact via additive migration 0003

- **Decision**: Add a `cadence` integer column (and a small `trigger_mode` string: `fixed` vs
  `compact_over_what_exists`) to `compaction_artifacts` through a new reversible Alembic migration
  `0003`. `save_artifact` records it; `get_artifacts`/`latest_artifact`/`export_cell` carry it
  through.
- **Rationale**: FR-004 requires the cadence be *recorded with each artifact*, not merely held in
  `Settings`. The table already stores `trigger_iteration` + `source_record_ids`; cadence is the
  missing lineage field. An additive, nullable-then-populated column mirrors migrations 0001/0002
  and the project's "Alembic-only, reversible" rule (Principle IV).
- **Alternatives considered**: Stash cadence inside the `artifact` JSONB (rejected — the belief
  schema is `extra="forbid"` and is a pure model projection, not lineage); stash in `cell.repro`
  like 005's fingerprint (rejected — cadence is *per-artifact* lineage, and a cell may in principle
  carry artifacts at one cadence; the artifact row is the correct home). Avoiding all schema change
  (rejected — would force lineage into a less inspectable place, against Principle IV).

## Decision 3 — Lineage audit is deterministic and LLM-free, beside the 005 verifier

- **Decision**: Add `verify_artifact_lineage(history_before, artifact_row)` and
  `audit_compaction(store, cell_id)` to `provenance.py`. For each persisted artifact, reconstruct
  from persisted history the exact id set of records with `iteration <= trigger_iteration` and
  assert it equals the recorded `source_record_ids`. No LLM calls.
- **Rationale**: Principle XII forbids silently dropping signal that cannot be audited against the
  raw trajectory; Principle IX requires verification from persisted state with no LLM calls. This
  exactly mirrors 005's `verify_cell` (rebuild-from-history-and-assert) and belongs in the same
  module to keep build (producer) and verify (auditor) split (Principle I).
- **Alternatives considered**: Semantic/content audit of *what beliefs* were dropped (rejected —
  would require an LLM judge, violating "third LLM job is the only one" and determinism; deferred to
  the 008 trajectory analysis at most). Coupling the audit into every run (rejected — FR-014: on
  demand, mirroring 004/005 CLI patterns).

## Decision 4 — Failure semantics: loud, specific, naming artifact + iteration

- **Decision**: A malformed operator output (non-conforming JSON) propagates as `LLMError`
  (fail-fast, already the 003 behavior, made explicit and tested). An audit failure returns/raises a
  typed result naming the offending `artifact_id`, the offending record id, and the
  `trigger_iteration`, distinguishing three modes: future-record-leaked, record-omitted,
  lineage-disagrees-with-history.
- **Rationale**: Principle X (loud, specific failure) and the 005 precedent (`ReplayMismatch` names
  the failing iteration). Naming the exact record/iteration makes the audit actionable.
- **Alternatives considered**: Boolean pass/fail (rejected — not actionable, hides which artifact).

## Decision 5 — Operator invariants pinned as tests, not new code paths

- **Decision**: No-future-leakage (`select_source` returns only `iteration <= trigger`),
  compact-over-what-exists (fewer than `m` records → compact whatever exists, log it), and
  degenerate-trajectory (all-failed/empty → still a valid artifact) are validated by tests against
  the existing functions with an injected hermetic `request_fn`.
- **Rationale**: These behaviors already exist in `compaction.py`; 006's job is to *guarantee* them
  (SC-001/002/003/006) and record the trigger mode used. Tests are the enforcement.
- **Alternatives considered**: Adding runtime assertions inside the loop (rejected — the audit
  already enforces lineage from persisted state; redundant in-loop asserts add noise).

## Decision 6 — Preserve the 005 memory seam verbatim

- **Decision**: `memory.py` `build_view` and its `_render_artifact` are untouched; the operator
  continues to hand `build_view` an opaque dict. 005's `verify_cell` and `audit_regimes` are run
  unchanged in tests against a `compacted_recent` cell backed by the operator.
- **Rationale**: FR-011/012/013 — 006's value depends on dropping in without disturbing the proven
  experimental backbone. The opaque-dict contract is the seam (contract restated in
  `contracts/compaction-operator.md`).
- **Alternatives considered**: Passing a typed `DirectionalMemory` into `build_view` (rejected —
  would change the 005 seam signature and break the opaque-dict guarantee).

## CLI surface

- **Decision**: Extend `ds-agent-memory` (entry `ds_agent_loop.provenance:main`) with a
  `compaction <cell_id>` subcommand printing each artifact's lineage (trigger, cadence, trigger mode,
  source record count) and the audit verdict. Backed by the reusable `audit_compaction` library
  function.
- **Rationale**: Mirrors the existing `replay`/`audit` subcommands and the 004 `benchmark` CLI; one
  consistent verification surface (FR-014).
