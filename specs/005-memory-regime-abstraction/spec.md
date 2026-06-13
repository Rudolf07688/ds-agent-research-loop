# Feature Specification: Memory-Regime Abstraction & Decision Provenance

**Feature Branch**: `005-memory-regime-abstraction`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "look at the progress html report and git logs and start drafting the next piece of the spec" — resolved, per `notes/progress.html` ("Next step on resume") and `notes/000-spec-list.md`, to roadmap entry **005 — Memory-Regime Abstraction & Decision Provenance**, the experimental backbone that turns memory into the single controlled variable on top of the now-fixed 004 benchmark.

## Overview

This feature makes **memory the only manipulated variable** in the autonomous-data-scientist loop
(constitution Principle XIII). It promotes the memory seam introduced provisionally during 003 into
a **first-class, configuration-selected abstraction**: one interface stands behind all three
regimes — **recent-only** (last `k` raw records), **all-raw** (the full raw history), and
**compacted+recent** (one Directional Research Memory artifact plus a short tail of fresh raw runs)
— and the regime is chosen per run as plain configuration, never as a fork of the loop.

Crucially, it binds that abstraction to the **004 benchmark suite**. A run is identified by
`(benchmark member, seed, regime)`; for a fixed `(member, seed)` everything else — agent, prompts,
action space, model allowlist, budget, frozen split, scoring — is held **provably identical** across
regimes, so any difference in behavior is attributable to memory alone.

It also hardens **decision provenance**. The **exact memory shown** to the agent before every
decision is persisted, content-addressably, and the feature adds a **verified replay** path: the
view for any recorded decision can be reconstructed deterministically from persisted history and
asserted to match the stored content hash. This proves every decision is replayable (Principle IX)
and lets two regimes be audited against each other from recorded state, not reconstructed guesswork.

This feature deliberately scopes to the **memory-regime interface, its provenance, and its
cross-regime invariants only**. It does **not** redefine or improve the Directional Research Memory
compaction operator itself (feature 006 owns the typed belief-schema artifact, its outer compaction
loop, and lineage), and it does **not** run the multi-dataset, multi-seed A/B/C study (feature 007).
For this feature the compacted regime consumes whatever compaction artifact already exists as an
opaque input; what 005 guarantees is that the *seam, the selection, and the provenance* are clean.

## Clarifications

### Session 2026-06-13

- Q: How should verified replay (US3) and cross-regime audit (US4) be exposed and invoked? → A: A thin CLI subcommand (`memory replay` / `memory audit`) backed by a library API, with the guarantees covered by tests — mirroring the 004 `benchmark` CLI and `analysis.py` reader patterns; verification is on demand, not coupled to every run.
- Q: For the compacted+recent regime to be runnable/testable in 005 (feature 006 not built yet), where does its compaction artifact come from? → A: Reuse the existing 003 `compaction.py` path as an opaque artifact producer, so the regime runs end-to-end now; 006 later replaces/hardens the operator without changing the 005 memory seam, and 005 adds no new LLM job.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Select a memory regime as pure configuration (Priority: P1)

As a researcher, I can run the loop against a benchmark member by id under any one of the three
memory regimes by selecting the regime (and its parameter `k`) purely through configuration, and the
loop body, prompts, action space, allowlist, budget, split, and scoring are identical regardless of
which regime I pick — only the slice of memory presented to the agent changes.

**Why this priority**: This is the irreducible mechanism of the thesis. Without a single interface
behind the regimes — selected as config, not a code fork — there is no clean causal claim about
memory, and features 006/007 have nothing to vary. A single regime-selectable run is itself the MVP.

**Independent Test**: Run the same `(member, seed)` three times, once per regime, changing only the
regime configuration. Confirm each run goes through the identical loop code path (no regime-specific
branch in the loop body beyond the single memory-view construction seam) and that the only observable
difference between runs is the memory shown to the agent.

**Acceptance Scenarios**:

1. **Given** a benchmark member id and a seed, **When** the regime is set to recent-only, all-raw,
   or compacted+recent via configuration, **Then** the loop runs to its budget under that regime with
   no regime-specific code path in the loop body other than the single memory-view seam.
2. **Given** a fixed `(member, seed)`, **When** the regime is changed, **Then** the prompts, action
   space, model allowlist, budget, frozen split, and scoring are byte-for-byte the same and only the
   rendered memory differs.
3. **Given** an unknown or malformed regime selection, **When** a run is configured, **Then** it is
   rejected at startup with a clear error rather than silently defaulting.

---

### User Story 2 - Record the exact memory shown before every decision (Priority: P1)

As a researcher, I can, for every decision the agent makes, retrieve the **exact memory view** that
was shown to it before that decision — the rendered text and the identifiers of every record/artifact
included — stamped with a content hash and keyed to `(member, seed, regime, iteration)`, so no
decision's context ever has to be reconstructed from guesswork.

**Why this priority**: "What the agent actually saw" is the evidence the entire study rests on
(Principle XIII). It must be captured at decision time, before the decision is recorded, and it is
needed before any cross-regime audit (US4) or study (007) can be trusted. It depends on US1's seam.

**Independent Test**: Run a member under one regime; for each iteration, confirm a persisted memory
view exists, is stamped with a content hash, lists the included record/artifact ids, is keyed to the
exact `(member, seed, regime, iteration)`, and that the experiment record for that iteration
references that view's hash.

**Acceptance Scenarios**:

1. **Given** a running loop, **When** the agent is about to make a decision at iteration `i`, **Then**
   the exact memory view shown is persisted **before** the resulting decision/experiment record is
   written.
2. **Given** a persisted memory view, **When** it is inspected, **Then** it carries the rendered
   memory text, the content hash, the ordered ids of every included record/artifact, and the
   `(member, seed, regime, iteration)` key.
3. **Given** a recorded decision, **When** it is queried, **Then** it references the content hash of
   the exact memory view that produced it, and that view is retrievable.

---

### User Story 3 - Replay any decision's memory view and verify it (Priority: P2)

As a researcher, I can re-derive the memory view for any recorded decision deterministically from the
persisted history under the recorded regime and parameters, and the harness asserts the reconstructed
view matches the stored content hash — proving the decision is replayable from recorded state without
new LLM calls.

**Why this priority**: Persistence alone (US2) shows what was seen; verified replay proves it is
*reproducible* (Principle IX) and that the provenance is trustworthy rather than merely stored. It
depends on US2's persisted views and US1's deterministic seam.

**Independent Test**: For a completed run, pick any recorded decision, reconstruct its memory view
from persisted history under the recorded regime/`k`/artifact, and confirm the reconstructed content
hash equals the stored hash; confirm replay performs no LLM calls and that a deliberately corrupted
view fails the check loudly.

**Acceptance Scenarios**:

1. **Given** a recorded decision and the persisted history up to it, **When** its memory view is
   replayed under the recorded regime and parameters, **Then** the reconstructed view is byte-identical
   and its content hash equals the stored hash.
2. **Given** a replay request, **When** it runs, **Then** it makes no LLM calls and uses only
   persisted state.
3. **Given** a persisted view whose content no longer matches its recorded hash, **When** verification
   runs, **Then** it fails loudly and specifically rather than passing silently.

---

### User Story 4 - Audit two regimes against each other (Priority: P2)

As a researcher, I can compare two runs of the same `(member, seed)` under different regimes and have
the harness confirm that everything except the memory shown was held identical, so any behavioral
difference is attributable to memory alone.

**Why this priority**: The clean causal claim ("memory is the sole intervention") must be checkable,
not assumed. This is the auditable guarantee that underpins the 007 study. It depends on US1–US3.

**Independent Test**: Run the same `(member, seed)` under two regimes; run the audit; confirm it
reports the held-fixed factors (prompts, action space, allowlist, budget, split, scoring,
seed) as identical across the two runs and surfaces the memory views as the differing factor; confirm
the audit fails if any held-fixed factor actually differs.

**Acceptance Scenarios**:

1. **Given** two runs of the same `(member, seed)` under different regimes, **When** the audit runs,
   **Then** it confirms the configuration fingerprint (excluding regime/memory) is identical across
   both runs.
2. **Given** the two runs, **When** the audit reports differences, **Then** it identifies the memory
   views (and the regime) as the differing dimension and exposes the per-iteration views for
   side-by-side inspection.
3. **Given** two runs that differ in a held-fixed factor (e.g. different budget or split), **When**
   the audit runs, **Then** it fails loudly identifying the contaminating variable.

---

### User Story 5 - Inspect and export memory provenance (Priority: P3)

As a researcher, I can inspect persisted memory views and their per-decision links directly in
Postgres and export them, per `(member, seed, regime)` cell, to human-readable JSON/CSV, so the
memory provenance is debuggable and reusable without database access.

**Why this priority**: Inspectability and export are constitutional (Principle IV) and make the
provenance trustworthy and portable, but they consume the artifacts produced by US2–US4, so they come
last.

**Independent Test**: Point the export at a completed cell; confirm it writes the per-iteration memory
views (text + included ids + hash) and their decision links to JSON/CSV that round-trip to
byte-identical data, and that the documented Postgres schema matches what was persisted.

**Acceptance Scenarios**:

1. **Given** a completed cell, **When** export runs, **Then** its per-iteration memory views and
   decision links are written as JSON/CSV that reload to byte-identical data.
2. **Given** the memory-provenance schema, **When** it is inspected, **Then** it is documented and was
   created/evolved exclusively through Alembic migrations (no ad-hoc DDL or operational `create_all`).
3. **Given** the persisted cell, **When** queried, **Then** the regime, parameters, exact memory per
   decision, and the configuration fingerprint are all retrievable for downstream attribution.

---

### Edge Cases

- **Empty history**: at the first decision (no prior records) every regime MUST produce a
  well-defined view (e.g. an explicit "no prior experiments yet" rendering), and that view MUST still
  be persisted and replayable.
- **`k` larger than available history**: recent-only and compacted+recent MUST clamp deterministically
  to whatever records exist (no error, no padding), and the clamp MUST be reflected in the recorded
  view.
- **All-raw exceeds the context window**: when the all-raw view would overflow the model context, the
  loop MUST halt the cell and record it as context-limited (never silently truncate the memory shown);
  the over-limit view that triggered the halt MUST itself be recorded.
- **Compacted regime with no artifact yet**: before the first compaction artifact exists, the
  compacted+recent regime MUST behave per a deterministic, recorded rule (compact-over-whatever-exists
  / recent-only fallback) so the regime is well-defined from iteration one; the rule applied MUST be
  recorded in the view.
- **Hash collision / mismatch on replay**: a reconstructed view whose hash diverges from the stored
  hash MUST fail loudly and identify the iteration, never be coerced to pass.
- **Regime/parameter drift mid-run**: changing the regime or `k` within a single `(member, seed)` cell
  MUST be rejected — a cell is one regime — so the controlled-variable invariant is never violated.
- **Audit across mismatched members/seeds**: an audit request comparing runs that are not the same
  `(member, seed)` MUST be rejected as not a valid memory-only comparison.

## Requirements *(mandatory)*

### Functional Requirements

**Regime abstraction (one interface, configuration-selected)**

- **FR-001**: The system MUST expose the three memory regimes — recent-only, all-raw, and
  compacted+recent — behind a single memory-view construction interface; the loop body MUST contain no
  regime-specific branching beyond that single seam.
- **FR-002**: The active regime and its parameter `k` MUST be selectable as configuration per run; an
  unknown or malformed regime selection MUST be rejected at startup, never silently defaulted.
- **FR-003**: For a fixed `(member, seed)`, the prompts, action space, model allowlist, budget, frozen
  split, and scoring MUST be identical across all regimes; the regime MUST change only the memory
  presented to the agent.
- **FR-004**: The memory-view interface MUST operate against any 004 benchmark member by id (using
  that member's frozen split and history), with no dataset-specific memory path.

**Decision provenance (exact memory shown)**

- **FR-005**: Before every agent decision, the system MUST persist the **exact** memory view shown —
  the rendered memory text and the ordered ids of every included record/artifact — stamped with a
  content hash and keyed to `(member, seed, regime, iteration)`.
- **FR-006**: The memory view MUST be persisted **before** the resulting decision/experiment record is
  written, and each experiment record MUST reference the content hash of the view that produced it.
- **FR-007**: For the all-raw regime, the view MUST never be silently truncated; if it would overflow
  the model context the cell MUST halt and be recorded as context-limited, with the over-limit view
  recorded.

**Verified replay (Principle IX)**

- **FR-008**: The system MUST reconstruct the memory view for any recorded decision deterministically
  from persisted history under that decision's recorded regime and parameters, performing no LLM calls.
- **FR-009**: Replay MUST assert the reconstructed view is byte-identical to the persisted view (equal
  content hash); a mismatch MUST fail loudly, identify the offending iteration, and never be coerced
  to pass.

**Cross-regime audit (memory is the only variable)**

- **FR-010**: The system MUST compute a configuration fingerprint per run that captures every held-fixed
  factor (prompts, action space, allowlist, budget, split, scoring, seed) and **excludes** the regime
  and the memory shown.
- **FR-011**: The system MUST provide an audit that, given two runs of the same `(member, seed)` under
  different regimes, confirms their configuration fingerprints are identical and reports the memory
  views (and regime) as the differing dimension; it MUST fail loudly if any held-fixed factor differs
  or if the runs are not the same `(member, seed)`.

**Invariants**

- **FR-012**: A single `(member, seed, regime)` cell MUST use one regime and one `k` for its entire
  lifetime; changing regime or `k` mid-cell MUST be rejected.
- **FR-013**: Every regime MUST produce a well-defined, persisted, replayable view for the
  empty-history first decision and MUST clamp `k` deterministically to available history.

**Operational surface**

- **FR-017**: Verified replay (FR-008/FR-009) and the cross-regime audit (FR-010/FR-011) MUST be
  invokable on demand as a thin CLI subcommand (e.g. `memory replay` / `memory audit`) backed by a
  reusable library API, with their guarantees covered by tests — mirroring the existing `benchmark`
  CLI and `analysis.py` reader patterns. Verification MUST NOT be coupled into every loop run.

**Persistence, inspectability & export**

- **FR-014**: All memory-provenance state (per-decision views, their included ids, content hashes,
  regime, parameters, and the configuration fingerprint) MUST be persisted in the single Postgres
  instance whose schema is documented and managed exclusively through Alembic migrations (no ad-hoc DDL
  or operational `create_all`).
- **FR-015**: Memory views and their per-decision links MUST be exportable, per `(member, seed, regime)`
  cell, to human-readable JSON/CSV that round-trips back to byte-identical data, so provenance is usable
  and inspectable without database access.

**Scope boundary**

- **FR-016**: This feature MUST treat the Directional Research Memory compaction artifact as an opaque
  input to the compacted+recent regime, consuming artifacts from the existing 003 `compaction.py` path
  so the regime is runnable and testable end-to-end now; defining, generating, or improving that
  artifact and its outer compaction loop is out of scope (feature 006, which MUST be able to replace the
  producer without changing the 005 memory seam), and running the multi-dataset/multi-seed A/B/C study
  is out of scope (feature 007). This feature MUST add no new LLM job.

### Key Entities *(include if feature involves data)*

- **Memory regime**: one of recent-only / all-raw / compacted+recent — a configuration value, not a
  code fork, that selects how the memory view is constructed.
- **Memory view**: the exact memory slice shown to the agent before one decision — rendered text plus
  the ordered ids of every included record/artifact, stamped with a content hash and keyed to
  `(member, seed, regime, iteration)`.
- **Experiment record / decision**: one iteration's outcome, referencing the content hash of the memory
  view that produced it.
- **Cell**: one `(member, seed, regime)` trajectory; one regime and one `k` for its lifetime.
- **Configuration fingerprint**: the digest of every held-fixed factor (prompts, action space,
  allowlist, budget, split, scoring, seed), excluding regime and memory — the basis of the cross-regime
  audit.
- **Compaction artifact**: the Directional Research Memory belief schema consumed (opaquely here) by
  the compacted+recent regime; owned by feature 006.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can run the same `(member, seed)` under all three regimes by changing only
  configuration, with no regime-specific branch in the loop body beyond the single memory-view seam.
- **SC-002**: For any two regimes over a fixed `(member, seed)`, every held-fixed factor (prompts,
  action space, allowlist, budget, split, scoring, seed) is provably identical and only the memory
  shown differs.
- **SC-003**: Every decision in a completed run has an associated persisted memory view, written before
  the decision record, content-hashed, listing its included ids, and keyed to
  `(member, seed, regime, iteration)`; the decision record references that hash.
- **SC-004**: Any recorded decision's memory view can be replayed from persisted state with no LLM
  calls, and the reconstructed content hash equals the stored hash for 100% of decisions in a run; a
  corrupted view fails the check loudly.
- **SC-005**: The cross-regime audit confirms configuration-fingerprint equality for two same-`(member,
  seed)` runs and fails loudly when a held-fixed factor differs or the runs are not the same
  `(member, seed)`.
- **SC-006**: Every regime yields a well-defined, persisted, replayable view at the empty-history first
  decision and clamps `k` deterministically to available history.
- **SC-007**: Memory views and their decision links export, per cell, to JSON/CSV that reloads to
  byte-identical data, and the Postgres schema backing memory provenance is documented and was created
  solely via Alembic migrations.

## Assumptions

- **The 003 memory seam is provisional, not final.** `memory.build_view`, the `MemoryView` model, the
  `memory_views` table, `store.save_view`, and `contracts/memory-view.md` exist from 003 but were built
  against the old single-dataset loop. This feature reconciles them with the 004 benchmark (member-keyed
  runs), promotes the seam to a first-class configuration-selected abstraction, and hardens provenance —
  extending and re-keying the existing code, not rewriting it from scratch.
- **Provenance is content-addressable with verified replay.** The exact memory shown is persisted and
  content-hashed (existing `memory_view_ref`), and this feature adds a deterministic replay path that
  reconstructs the view from persisted history and asserts hash equality (chosen approach over
  store-only).
- **Benchmark, splits, budgets, action spaces, and allowlists are fixed inputs** supplied by feature
  004 and loaded by member id; this feature does not redefine them.
- **The compaction artifact is an opaque input here, produced by the existing 003 path.** The
  compacted+recent regime consumes artifacts from the existing `compaction.py` (003) as an opaque
  producer, so the regime runs end-to-end now; the typed belief schema, its generation, the outer
  compaction loop, and full lineage are feature 006, which must be able to swap in without changing the
  005 memory seam. 005 adds no new LLM job.
- **One regime per cell.** A `(member, seed, regime)` cell is immutable in regime and `k`; multi-regime
  comparison happens across cells, and the full multi-seed/multi-dataset study is feature 007.
- **LLM backend is the current Vertex AI / Gemini + minimal ADK setup** (feature 002); this feature
  adds no new LLM job. Replay and audit are deterministic and make no LLM calls.
- **Schema is owned by Alembic.** Any new/changed memory-provenance tables ship as reviewed Alembic
  migrations applied with `alembic upgrade head` (constitution Principle IV); `create_all` is restricted
  to ephemeral/test schemas.
- **The token estimate is the existing deterministic proxy** (~4 chars/token) used to detect all-raw
  context overflow offline; it is a reproducible measure, not a billing figure.

## Dependencies

- Builds directly on feature **004** (versioned benchmark suite: frozen splits, budgets, action spaces,
  allowlists, member-by-id loading) and the Postgres + Alembic persistence established around features
  003/004 (commits `130ef01`, `190537b`, `3d0a621`).
- Reconciles and generalizes existing modules — `memory.py` (`build_view`, three regimes), `prompts.py`
  (`MemoryView`, `MemoryRegime`, `memory_view_ref`), `store.py` (`memory_views` table, `save_view`,
  `get_views`), `main.py` (per-decision view persistence), `analysis.py` (export readers), and
  `compaction.py` (the opaque 003 artifact producer for the compacted regime) — extended and re-keyed to
  benchmark members, not replaced.
- **Postgres** (single instance) for durable memory-provenance persistence, orchestrated locally by the
  root `docker-compose.yml` and reached via `DATABASE_URL`; schema changes ship as **Alembic** migrations.
- **Unblocks** feature **006** (Directional Research Memory compaction operator — the compacted regime's
  artifact and outer loop), feature **007** (A/B/C ablation study across the full benchmark and many
  seeds), and downstream **008–010** — none of which can make a clean memory-only causal claim without
  this abstraction and its verified provenance.
- The project **constitution** (v5.3.0) governs: Principle XIII (memory as the sole controlled variable,
  exact memory shown recorded), Principle IX (reproducible/replayable experiments), and Principle IV
  (inspectable, exportable, Alembic-managed state) are the primary constraints this feature satisfies.
  Thesis chapter 3.
