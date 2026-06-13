# Feature Specification: Directional Research Memory Compaction Operator

**Feature Branch**: `006-directional-research-memory-compaction-operator`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Use `notes/006-start-here.md` and the progress html file to start with the next spec" — resolved, per `notes/006-start-here.md`, `notes/progress.html` ("Next step on resume"), and `notes/000-spec-list.md`, to roadmap entry **006 — Directional Research Memory Compaction Operator**, the precise, audited definition of the compaction operator that the `compacted_recent` regime consumes.

## Overview

This feature makes the **compaction operator a first-class, sanctioned, fully auditable
operator** rather than the opaque artifact producer that the `compacted_recent` regime
consumes today (constitution Principle XII). 005 made memory the sole experimental variable and
proved every decision replayable; it deliberately left the *producer* of the compacted artifact
opaque — reusing the 003 `compaction.py` path as-is. 006 supersedes and hardens that producer.

The operator projects the raw experiment trajectory onto a **typed belief schema** — what is
probably **TRUE**, what has likely **FAILED**, what remains **UNRESOLVED**, and which broad
**DIRECTIONS** in experiment space are worth pursuing next — as the **third (and only third)
sanctioned LLM job** (Principle II). It runs in an **explicit outer compaction loop** distinct
from the inner experiment loop: on a recorded cadence the trajectory recorded so far is re-read
and (re)projected into a single artifact, rather than appended to an ever-growing raw history.
The **compaction cadence is an explicit, recorded parameter**, and every artifact carries **full
source→artifact lineage** so it can be traced to the exact raw runs it summarized.

Crucially, the operator must be **auditable against the raw trajectory it replaced**: the system
can prove, from persisted state and without new LLM calls, that an artifact was produced only from
records at or before its trigger (no future-outcome leakage) and that the raw signal it claims to
summarize is actually covered by its inputs — so signal is never *silently* dropped in a way that
cannot be checked.

This feature is bounded to the **operator, its outer loop, its lineage, and its audit**. It
**preserves the 005 memory seam unchanged**: `memory.build_view` continues to take the artifact as
an **opaque dict**, so verified-replay (`provenance.verify_cell`) and the cross-regime audit
(`provenance.audit_regimes`) keep working exactly as in 005. It does **not** alter the recent-only
or all-raw regimes, does **not** change the regime-selection or decision-provenance contracts, and
does **not** run the multi-dataset, multi-seed A/B/C study (feature 007).

## Clarifications

### Session 2026-06-13

- Q: How should the explicit cadence be persisted with each artifact (FR-004)? → A: Add `cadence` (+ `trigger_mode`) columns to `compaction_artifacts` via an additive, reversible Alembic migration (0003) — most inspectable, matches Principle IV and the 0001/0002 precedent.
- Q: Is the optional token-threshold trigger (003's secondary `should_compact` mode) in scope, and how is it recorded? → A: Keep both fixed-cadence and token-threshold triggers; record which fired via `trigger_mode` (`fixed` | `compact_over_what_exists` | `token_threshold`).
- Q: How should the audit treat pre-006 artifacts with no recorded cadence (NULL after the additive migration)? → A: Tolerate — a NULL cadence means "unrecorded (pre-006)"; the lineage audit still runs on `source_record_ids` and passes, reporting cadence as unknown. No backfill.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce the typed Directional Research Memory artifact on an explicit cadence (Priority: P1)

As a researcher, I can have the loop run an **outer compaction loop** that, on an explicit and
recorded cadence, re-reads the trajectory so far and produces one **schema-constrained belief
artifact** — confirmed findings, failed directions, promising directions, best-known configs,
unresolved questions, a single next-step recommendation, a confidence, and a rationale — as the
only third sanctioned structured-JSON LLM job, never as free-form prose.

**Why this priority**: This is the central object of the thesis (Principle XII). Without a precise,
schema-pinned operator fired on a recorded cadence, "compaction helps" is not a testable claim and
the `compacted_recent` regime has nothing well-defined to consume. A single cadence-driven artifact
generation is itself the MVP.

**Independent Test**: Run a cell with a chosen cadence and confirm the artifact is generated at the
expected trigger iterations, conforms to the belief schema (all required fields present, types and
bounds enforced, no extra fields), and that a malformed projection is rejected loudly rather than
silently accepted.

**Acceptance Scenarios**:

1. **Given** a cell configured with an explicit compaction cadence, **When** the run reaches a
   trigger iteration, **Then** exactly one belief artifact is produced from the trajectory and
   persisted, and the cadence used is recorded with it.
2. **Given** a trigger iteration, **When** the operator runs, **Then** it sees **only** experiment
   records at or before that iteration and never any later outcome.
3. **Given** the operator's output, **When** it does not conform to the belief schema (missing
   field, out-of-range confidence, extra field, or non-JSON), **Then** the run fails fast with a
   clear error rather than persisting a malformed artifact.
4. **Given** a trigger reached before the cadence window is full, **When** the operator runs,
   **Then** it compacts over whatever records exist (deterministically) and records that it did so.

---

### User Story 2 - Trace every artifact to the exact raw runs it summarized (Priority: P1)

As a researcher, I can take any persisted compaction artifact and recover its **full lineage** —
which cell it belongs to, the trigger iteration, and the exact set of source experiment records
(by identity) it was produced from — so any belief artifact is traceable end-to-end to the raw
trajectory it replaced (Principle IV).

**Why this priority**: Lineage is what makes the operator inspectable and the thesis defensible. An
artifact whose inputs cannot be enumerated cannot be audited, reproduced, or trusted. Lineage is a
P1 companion to generation.

**Independent Test**: Generate one or more artifacts in a cell, then retrieve each artifact's
recorded source-record identities and confirm they exactly match the records at or before the
trigger iteration that existed when it was produced.

**Acceptance Scenarios**:

1. **Given** a persisted artifact, **When** its lineage is read, **Then** it names its cell, its
   trigger iteration, the recorded cadence, and the identity of every source record it summarized.
2. **Given** a cell with multiple compaction triggers, **When** lineage is read across artifacts,
   **Then** each artifact's source set corresponds to its own trigger window and the artifacts are
   ordered by trigger iteration.
3. **Given** an artifact's recorded source set, **When** compared to the persisted raw history at
   its trigger, **Then** the source set contains exactly the records at or before the trigger and
   no later record.

---

### User Story 3 - Audit that the operator did not silently drop signal (Priority: P2)

As a researcher, I can run an **on-demand audit** of any artifact that verifies, from persisted
state and **without any LLM calls**, that the artifact respects its lineage — produced only from
records at or before its trigger (no future leakage) and covering exactly its declared source set —
so the operator cannot silently discard raw signal in a way that cannot be checked against the
trajectory it replaced (Principle XII).

**Why this priority**: Principle XII forbids silently dropping signal that cannot be audited against
the raw trajectory. This audit is the mechanism that enforces it. It is P2 because generation and
lineage (P1) must exist first, but it is required before the operator can be trusted in a study.

**Independent Test**: Run the audit over a cell's artifacts and confirm a well-formed artifact
passes, while a tampered artifact (one whose recorded source set includes a future record, omits a
record at/before the trigger, or whose lineage disagrees with persisted history) fails loudly with
the offending artifact and iteration named.

**Acceptance Scenarios**:

1. **Given** a faithfully produced artifact, **When** the audit runs, **Then** it passes with no
   LLM calls and reports the source coverage it verified.
2. **Given** an artifact whose recorded source set includes a record after its trigger iteration,
   **When** the audit runs, **Then** it fails and names the leaking record and the artifact.
3. **Given** an artifact whose source set omits a record at or before its trigger, **When** the
   audit runs, **Then** it fails and names the missing record and the artifact.

---

### User Story 4 - Swap in as the compacted regime's producer without changing the 005 seam (Priority: P2)

As a researcher, I can use the 006 operator as the producer of the artifact consumed by the
`compacted_recent` regime, with the **005 memory seam unchanged**: `memory.build_view` still
receives the artifact as an opaque dict, so verified-replay and the cross-regime audit from 005
keep passing without modification.

**Why this priority**: 006's value is realized only if it drops into the existing experimental
backbone without disturbing the proven 005 guarantees. This protects the work 005 delivered and
keeps the compacted regime runnable end-to-end. P2 because it depends on US1–US2 existing.

**Independent Test**: Run the `compacted_recent` regime end-to-end using the 006 operator, then run
the 005 `provenance.verify_cell` and `provenance.audit_regimes` paths and confirm they pass
unchanged — the memory-view content hashes still replay and the cross-regime fingerprint still
proves memory is the only difference.

**Acceptance Scenarios**:

1. **Given** the `compacted_recent` regime backed by the 006 operator, **When** a cell runs to
   budget, **Then** the artifact is consumed through the existing `build_view` opaque-dict contract
   with no change to that seam's inputs or outputs.
2. **Given** a completed `compacted_recent` cell, **When** 005 verified-replay runs, **Then** every
   decision's memory view still replays to its stored content hash.
3. **Given** two cells of one `(member, seed)` differing only in regime, **When** the 005
   cross-regime audit runs, **Then** it still proves they differ only in memory.

---

### Edge Cases

- **Compaction at iteration 0 / before any experiment**: no trigger fires until at least the first
  record exists; a cadence of 0 or negative is rejected as configuration.
- **Re-compaction at the same trigger**: regenerating an artifact for an existing
  `(cell, trigger_iteration)` replaces it idempotently rather than creating a duplicate.
- **Fewer than a full cadence window at a trigger**: the operator compacts over whatever records
  exist and records that it did so (compact-over-what-exists, deterministic and logged).
- **Empty / degenerate trajectory** (all experiments failed or rejected): the operator still emits
  a valid artifact (e.g. empty finding lists with an unresolved-questions entry), never a malformed
  one.
- **Malformed LLM output**: rejected loudly as an error; no partial or coerced artifact is persisted.
- **Lineage disagreement**: if a stored artifact's source set cannot be reconciled with persisted
  history, the audit fails and names the artifact and iteration rather than passing silently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST produce the Directional Research Memory artifact as a typed,
  schema-constrained structure capturing at minimum: what is probably TRUE, what has likely FAILED,
  what remains UNRESOLVED, and which broad DIRECTIONS are worth pursuing next; free-form prose alone
  MUST NOT satisfy this requirement.
- **FR-002**: Compaction MUST be the only third sanctioned LLM job and MUST emit structured JSON
  validated against the belief schema; any non-conforming output MUST fail fast.
- **FR-003**: The operator MUST run in an outer compaction loop, distinct from the inner experiment
  loop, that re-reads the recorded trajectory and (re)generates the artifact rather than appending
  to an ever-growing raw history.
- **FR-004**: The compaction cadence MUST be an explicit configuration parameter and MUST be
  recorded with each artifact it produces, persisted in a dedicated, inspectable field on the
  artifact's lineage (added via an additive, reversible schema migration).
- **FR-005**: Compaction MUST see only experiment records at or before the trigger iteration and
  MUST never have access to any later outcome (no future-outcome leakage).
- **FR-006**: When fewer than a full cadence window of records exists at a trigger, the operator
  MUST compact over whatever records exist deterministically and record that it did so.
- **FR-006a**: Each artifact MUST record the trigger mode that fired it — one of `fixed`
  (fixed-cadence), `compact_over_what_exists` (short window), or `token_threshold` (the optional
  secondary trigger, which remains in scope) — so the trigger reason is auditable, not inferred.
- **FR-006b**: Artifacts produced before this feature (with no recorded cadence) MUST be tolerated:
  a missing cadence is treated as "unrecorded (pre-006)" and the lineage audit still runs on the
  recorded source records and passes; no backfill of historical cadence is performed.
- **FR-007**: Every artifact MUST be persisted with full source→artifact lineage: its cell, its
  trigger iteration, the recorded cadence, and the identity of every source record it summarized.
- **FR-008**: The system MUST provide an on-demand audit that verifies, from persisted state and
  without any LLM calls, that an artifact respects its lineage — produced only from records at or
  before its trigger and covering exactly its declared source set.
- **FR-009**: The audit MUST fail loudly and name the offending artifact and iteration when an
  artifact's source set includes a future record, omits a record at or before its trigger, or
  otherwise disagrees with persisted history.
- **FR-010**: Re-generating an artifact for an existing `(cell, trigger_iteration)` MUST replace it
  idempotently and MUST NOT create duplicate lineage.
- **FR-011**: The operator MUST be usable as the producer for the `compacted_recent` regime through
  the existing 005 `memory.build_view` opaque-dict contract, with **no change** to that seam's
  inputs or outputs.
- **FR-012**: The 005 verified-replay (`provenance.verify_cell`) and cross-regime audit
  (`provenance.audit_regimes`) guarantees MUST continue to hold unchanged when the compacted regime
  is backed by the 006 operator.
- **FR-013**: The operator MUST NOT alter the recent-only or all-raw regimes, the regime-selection
  contract, or the decision-provenance contract established in 005.
- **FR-014**: The audit MUST be exposed through a thin CLI subcommand backed by a library API,
  mirroring the existing `ds-agent-memory replay|audit` and `benchmark` CLI patterns; verification
  is on demand, not coupled to every run.

### Key Entities *(include if feature involves data)*

- **Directional Research Memory artifact**: the typed belief-schema projection of the trajectory —
  confirmed findings, failed directions, promising directions, best-known configs, unresolved
  questions, a single next-step recommendation, a confidence in [0,1], and a rationale.
- **Compaction trigger**: a point in a cell's run, determined by the explicit cadence, at which the
  outer loop fires and an artifact is (re)generated.
- **Artifact lineage**: the persisted association of an artifact with its cell, trigger iteration,
  recorded cadence, trigger mode (`fixed` | `compact_over_what_exists` | `token_threshold`), and the
  identities of the exact source records it summarized.
- **Compaction audit result**: the outcome of the on-demand, no-LLM audit — pass with verified
  source coverage, or fail naming the offending artifact, record, and iteration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any cell with an explicit cadence, an artifact is produced at every expected
  trigger iteration and at no other iteration; 100% of produced artifacts conform to the belief
  schema.
- **SC-002**: 100% of malformed or non-conforming operator outputs are rejected with a clear error;
  no malformed artifact is ever persisted.
- **SC-003**: 100% of produced artifacts are summarized from records at or before their trigger; a
  test injecting a future record into an artifact's source set is detected and rejected by the audit.
- **SC-004**: Every persisted artifact's lineage uniquely resolves its cell, trigger iteration,
  cadence, and complete source-record identity set; the audit verifies source coverage with **zero**
  LLM calls.
- **SC-005**: When the `compacted_recent` regime is backed by the 006 operator, the full 005
  verified-replay and cross-regime audit suites pass unchanged (no regression in the 005 guarantees).
- **SC-006**: Re-running compaction for an existing `(cell, trigger_iteration)` yields exactly one
  artifact (idempotent replace), never a duplicate.
- **SC-007**: The offline test suite remains green and grows to cover cadence triggering,
  schema/fail-fast, no-future-leakage, lineage completeness, audit pass/tamper, idempotent
  re-compaction, and the unchanged-seam guarantee (building on the 121 tests passing as of 005).

## Assumptions

- The belief schema and the existing `compaction.py` producer introduced in 003 (the
  `DirectionalMemory` model, `COMPACTION_SCHEMA`, `should_compact`, `select_source`, `compact`) are
  the starting point 006 hardens and formalizes — not a rewrite from scratch — and the `confidence`
  and `rationale` fields are retained as part of the schema-pinned artifact.
- The existing `compaction_artifacts` table and `save_artifact`/`get_artifacts`/`latest_artifact`
  store API are the persistence substrate; lineage is recorded by extending what is already stored
  (source-record identities, plus the cadence and trigger mode added via an additive, reversible
  Alembic migration) rather than redefining the memory seam.
- The compaction cadence parameter is centralized in `Settings` (Principle VIII), selected per run
  as configuration alongside the 005 `regime` and `k`.
- Verification (lineage audit) is invoked on demand via the existing `ds-agent-memory` CLI surface,
  consistent with the 004/005 CLI-plus-library pattern, not coupled into every run.
- Source-record identity is the existing experiment-record identity persisted in the store; no new
  identifier scheme is introduced.
- This feature stays within the existing offline-testable harness; live LLM verification is out of
  scope here and governed by feature 002's live-test path.
