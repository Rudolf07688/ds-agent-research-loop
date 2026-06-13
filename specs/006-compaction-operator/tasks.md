---
description: "Task list for Directional Research Memory Compaction Operator"
---

# Tasks: Directional Research Memory Compaction Operator

**Input**: Design documents from `/specs/006-compaction-operator/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — the project is test-driven and SC-007 requires the offline suite to grow to
cover cadence triggering, schema/fail-fast, no-future-leakage, lineage, audit pass/tamper, the
migration, and the unchanged-seam guarantee.

**Organization**: Tasks grouped by user story. This feature **hardens + verifies** the existing
003 producer; it is not a rewrite. `memory.py` is untouched (005 seam preserved).

## Path Conventions

Single `src`-layout research library: `src/ds_agent_loop/`, `tests/`, `alembic/versions/` at repo root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the workspace is ready; no new dependencies.

- [X] T001 Verify environment and current green baseline: run `uv sync` and `uv run pytest` from repo root, confirming the 121-test suite passes before any change.
- [X] T002 Re-read the seam-preservation constraint in `src/ds_agent_loop/memory.py` (`build_view` / `_render_artifact`) and note in a scratch comment that it MUST remain byte-for-byte unchanged (FR-011/013); no edits in this phase.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The persistence substrate that BOTH US1 (cadence recording) and US2 (lineage) build
on. MUST complete before US1/US2.

- [X] T003 Add Alembic migration `alembic/versions/0003_compaction_cadence.py`: additive, nullable `cadence INTEGER` and `trigger_mode VARCHAR` columns on `compaction_artifacts`; `down_revision = "0002"`; reversible `upgrade()`/`downgrade()` (drop both columns). No data backfill (FR-006b).
- [X] T004 Extend the `compaction_artifacts` Table definition in `src/ds_agent_loop/store.py` with the `cadence` and `trigger_mode` columns so SQLAlchemy Core matches migration 0003.
- [X] T005 Update `Store.save_artifact` in `src/ds_agent_loop/store.py` to accept `cadence: int | None` and `trigger_mode: str` params, persist them, and include them in the `on_conflict_do_update` set_ (idempotent replace, FR-010).
- [X] T006 Mirror the new columns/params in `FakeStore.save_artifact` and `_artifacts` storage in `src/ds_agent_loop/store.py`, keeping `get_artifacts`/`latest_artifact` returning `cadence`/`trigger_mode` (read back `None` when unrecorded).
- [X] T007 Extend `export_cell` in `src/ds_agent_loop/store.py` so `artifacts.json` carries `cadence` and `trigger_mode` per artifact (inspectable export, Principle IV).
- [X] T008 [P] Add typed models to `src/ds_agent_loop/prompts.py`: `LineageMismatch` (artifact_id, trigger_iteration, kind, record_id, detail) and `CompactionAuditResult` (cell_id, artifacts_checked, ok, llm_calls, mismatches), per data-model.md.

**Checkpoint**: schema + store + typed result models exist; suite still green (migration applied).

---

## Phase 3: User Story 1 — Produce the typed artifact on an explicit cadence (Priority: P1)

**Goal**: The outer compaction loop produces a schema-conforming belief artifact at the recorded
cadence, sees only at/before-trigger records, fails fast on malformed output, and records the
trigger mode used.

**Independent Test**: Run a cell with a chosen cadence; confirm artifacts appear at exactly the
trigger iterations, conform to the belief schema, malformed output is rejected, and `cadence` +
`trigger_mode` are recorded.

- [X] T009 [P] [US1] Harden `select_source` in `src/ds_agent_loop/compaction.py`: pin the no-future-leakage invariant (only `iteration <= trigger_iteration`) with a clear docstring/assert; no behavior change.
- [X] T010 [US1] Update the outer compaction loop in `src/ds_agent_loop/main.py` (`run_cell`, near the existing `should_compact`/`select_source`/`save_artifact` block) to compute the `trigger_mode` actually used (`fixed` | `compact_over_what_exists` | `token_threshold`) and pass `cadence=m` and `trigger_mode` into `store.save_artifact`; extend the `compaction_done` log with `cadence` and `mode`.
- [X] T011 [US1] Make schema fail-fast explicit in `src/ds_agent_loop/compaction.py` `compact`: ensure non-conforming/malformed `request_fn` output propagates as `LLMError` and is never persisted (FR-002); add a guard/docstring.
- [X] T012 [P] [US1] Tests in `tests/test_compaction.py`: cadence trigger points (fires at every m-th, not between); no-future-leakage of `select_source`; compact-over-what-exists for a short window sets `trigger_mode=compact_over_what_exists`; degenerate (all-failed/empty) trajectory still yields a valid artifact (SC-001/006, edge cases).
- [X] T013 [P] [US1] Test in `tests/test_compaction.py`: malformed/non-conforming operator output (via injected hermetic `request_fn`) raises `LLMError` and persists no artifact (SC-002).
- [X] T014 [US1] Test in `tests/test_loop.py`: a `compacted_recent` cell run with cadence `m` records `cadence` and the correct `trigger_mode` on every artifact (FR-004/006a); re-running a trigger yields exactly one artifact (SC-006).

**Checkpoint**: artifacts generated, schema-validated, cadence + trigger mode recorded.

---

## Phase 4: User Story 2 — Trace every artifact to the exact raw runs it summarized (Priority: P1)

**Goal**: Every persisted artifact's lineage resolves its cell, trigger iteration, cadence, trigger
mode, and the exact source-record identities; source set = records at/before trigger, no later.

**Independent Test**: Generate artifacts in a cell, read each artifact's recorded source-record
identities, and confirm they exactly match the records at/before the trigger that existed then.

- [X] T015 [P] [US2] Test in `tests/test_store_integration.py` (Postgres, skipped when no DB): migration 0003 upgrade → downgrade → upgrade is reversible and idempotent; `cadence`/`trigger_mode` round-trip through `save_artifact`/`get_artifacts`.
- [X] T016 [P] [US2] Test in `tests/test_loop.py` (or `test_compaction.py`): for a multi-trigger cell, each artifact's `source_record_ids` equals the id set of records with `iteration <= trigger_iteration`, artifacts are ordered by trigger iteration, and no later record appears (FR-005/007, SC-003 lineage half).
- [X] T017 [US2] Verify/extend `export_cell` round-trip test so exported `artifacts.json` includes complete lineage (cell, trigger_iteration, cadence, trigger_mode, source_record_ids).

**Checkpoint**: lineage is complete and persisted; US1+US2 together give a recorded, traceable operator.

---

## Phase 5: User Story 3 — Audit that the operator did not silently drop signal (Priority: P2)

**Goal**: An on-demand, deterministic, no-LLM audit proves each artifact respects its lineage and
fails loudly (naming artifact + iteration) on tamper; exposed via the `ds-agent-memory` CLI.

**Independent Test**: Run the audit over a cell; a faithful artifact passes with 0 LLM calls; a
tampered artifact (future record / omitted record / history disagreement) fails loudly.

- [X] T018 [US3] Implement `verify_artifact_lineage(artifact_row, history)` in `src/ds_agent_loop/provenance.py`: reconstruct `{ r.id for r in history if r.iteration <= trigger_iteration }`, compare to recorded `source_record_ids`, return `LineageMismatch | None` distinguishing `future_record_leaked` / `record_omitted` / `history_disagreement` (FR-008/009).
- [X] T019 [US3] Implement `audit_compaction(store, cell_id) -> CompactionAuditResult` in `src/ds_agent_loop/provenance.py`: load artifacts (in trigger order) + history, run `verify_artifact_lineage` per artifact, perform zero LLM calls, aggregate `ok`/`mismatches`/`artifacts_checked`/`llm_calls=0`; tolerate NULL cadence as "unrecorded (pre-006)" (FR-006b).
- [X] T020 [US3] Add the `compaction <cell_id>` subcommand to `main()` in `src/ds_agent_loop/provenance.py` beside `replay`/`audit`: print per-artifact trigger_iteration/cadence/trigger_mode/source-count and the verdict (`OK (n artifacts, 0 LLM calls)` or each mismatch), non-zero exit on failure (FR-014).
- [X] T021 [P] [US3] Tests in `tests/test_provenance.py`: faithful cell audit passes with `llm_calls == 0` and correct `artifacts_checked` (SC-003/004); a NULL-cadence (pre-006) artifact is tolerated and still lineage-audited (FR-006b).
- [X] T022 [P] [US3] Tests in `tests/test_provenance.py`: tampered source set fails loudly naming artifact + record + iteration for each kind — future record injected (`future_record_leaked`), record omitted (`record_omitted`), recorded id absent from history (`history_disagreement`) (FR-009, SC-003).

**Checkpoint**: the operator is auditable; silent signal drop is detectable from persisted state.

---

## Phase 6: User Story 4 — Swap in without changing the 005 seam (Priority: P2)

**Goal**: The `compacted_recent` regime backed by the operator runs end-to-end and the 005
verified-replay + cross-regime audit pass unchanged.

**Independent Test**: Run a `compacted_recent` cell, then run 005 `verify_cell` and `audit_regimes`
and confirm they pass unchanged.

- [X] T023 [US4] Confirm `memory.build_view` and `_render_artifact` in `src/ds_agent_loop/memory.py` are unchanged (opaque-dict contract intact); add a focused assertion/comment if needed (FR-011).
- [X] T024 [P] [US4] Test in `tests/test_loop.py` (or `test_memory.py`): for a `compacted_recent` cell produced by the 006 operator, `provenance.verify_cell` replays every decision's memory view to its stored content hash (FR-012, SC-005).
- [X] T025 [P] [US4] Test in `tests/test_provenance.py`: two cells of one `(member, seed)` differing only in regime still pass `audit_regimes` (differ only in memory) with the operator-backed compacted cell (FR-012, SC-005).

**Checkpoint**: 006 drops into the 005 backbone with no regression.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T026 [P] Update `README.md` with the `ds-agent-memory compaction <cell_id>` usage and the cadence/trigger-mode/lineage concepts.
- [X] T027 [P] Refresh `notes/progress.html` with a "What 006 delivers" section (operator hardened, cadence + trigger mode recorded, lineage audit, migration 0003, seam unchanged) and the new test count.
- [X] T028 Run the full `uv run pytest` suite (offline + Postgres integration) and confirm all tasks' guarantees hold and the suite is green and grown (SC-007).
- [X] T029 Run `detect_changes({scope: "compare", base_ref: "main"})` (per CLAUDE.md) to confirm only the expected symbols/flows changed before handing off to commit.

---

## Dependencies & Story Completion Order

- **Setup (T001–T002)** → **Foundational (T003–T008)** → user stories.
- **US1 (T009–T014)** and **US2 (T015–T017)** both depend only on Foundational; US2's lineage assertions assume US1 records artifacts, so complete US1 first in practice (both P1).
- **US3 (T018–T022)** depends on US1+US2 (needs recorded artifacts + lineage to audit).
- **US4 (T023–T025)** depends on US1 (needs operator-backed compacted cells); independent of US3.
- **Polish (T026–T029)** last.

```
Setup → Foundational ─┬→ US1 ─┬→ US3 ─┐
                      │       │       ├→ Polish
                      └→ US2 ─┘       │
                         └─→ US4 ─────┘
```

## Parallel Execution Examples

- **Foundational**: T008 (typed models) ∥ T003–T007 are mostly same-file (`store.py`) so serialize T004–T007; T003 (migration) and T008 (prompts) can run alongside.
- **US1**: T009 (`compaction.py`) ∥ T012/T013 (`test_compaction.py`) once T010 lands; T014 (`test_loop.py`) parallel to compaction tests.
- **US2**: T015 (`test_store_integration.py`) ∥ T016 (`test_loop.py`).
- **US3**: T021 ∥ T022 (both `test_provenance.py`, distinct cases) after T018–T020.
- **US4**: T024 ∥ T025 after T023.
- **Polish**: T026 ∥ T027.

## Implementation Strategy

- **MVP = US1 (+ Foundational)**: a cadence-driven, schema-validated, cadence-recorded artifact is
  the irreducible Principle XII deliverable.
- **Then US2** for full lineage, **US3** for the auditability guarantee (the feature's core new
  value), and **US4** to prove the 005 backbone is undisturbed.
- Keep `memory.py` untouched throughout; per CLAUDE.md run `impact` before editing `save_artifact`,
  `run_cell`, or the `compaction` functions, and `detect_changes` before committing.
