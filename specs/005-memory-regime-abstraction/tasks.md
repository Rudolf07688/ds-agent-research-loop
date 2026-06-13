---
description: "Task list for 005 — Memory-Regime Abstraction & Decision Provenance"
---

# Tasks: Memory-Regime Abstraction & Decision Provenance

**Input**: Design documents from `/specs/005-memory-regime-abstraction/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: Included — constitution Principle XI requires tests for the deterministic verification
layer, and the plan names specific test modules. Replay/audit are pure and LLM-free, so tests run
offline.

**Organization**: Grouped by user story (US1–US5) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 for story phases; Setup/Foundational/Polish carry no story label
- All paths are repo-relative; single `src`-layout project (`src/ds_agent_loop/`, `tests/`)

## Context (what already exists from 003/004 — do NOT rebuild)

- `memory.build_view` — the three-regime seam (unchanged this feature)
- `prompts.MemoryView` + `store.memory_views` table + `save_view`/`get_views`
- `run_cell` persists the view **before** each decision and links `memory_view_ref`
- all-raw context-limit halt, empty-history/`k`-clamp, compacted fallback
- per-cell JSON/CSV export (`store.export`, `analysis.py` readers)
- 004 `materialize_suite` / `load_member`, `benchmark` CLI, `ExperimentCell.repro` (JSONB)

**No new tables and no Alembic migration in this feature** (the config fingerprint rides in
`ExperimentCell.repro`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the one new module and its CLI registration so all stories have a home.

- [X] T001 Create `src/ds_agent_loop/provenance.py` module skeleton (module docstring citing Principles IX/XIII, `from __future__ import annotations`, imports of `memory`, `store`, `benchmark`, `prompts`) — empty function stubs for `replay_view`, `verify_cell`, `config_fingerprint`, `audit_regimes`, `main`.
- [X] T002 Add the `ds-agent-memory = "ds_agent_loop.provenance:main"` console entry under `[project.scripts]` in `pyproject.toml`.
- [X] T003 [P] Create empty test module `tests/test_provenance.py` with offline/`FakeStore` fixtures mirroring `tests/test_loop.py` conventions.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Result models and the deterministic helpers every story depends on. MUST complete before US1–US5.

- [X] T004 [P] Add `ReplayResult`, `ReplayMismatch`, and `AuditResult` Pydantic models (per `data-model.md`) to `src/ds_agent_loop/prompts.py` (`extra="forbid"`, typed fields).
- [X] T005 Implement `provenance.config_fingerprint(cell, descriptor)` in `src/ds_agent_loop/provenance.py` — canonical sorted-key JSON over held-fixed factors (prompt/schema version, action space, allowlist, budget, patience, `split_ref`+`benchmark_version`, primary metric+direction, seed), SHA-256; explicitly EXCLUDE `regime`, `k`, and memory content (research Decision 2, FR-010).

**Checkpoint**: Models import cleanly; `config_fingerprint` is deterministic and order-independent.

---

## Phase 3: User Story 1 — Select a memory regime as pure configuration (Priority: P1) 🎯 MVP

**Goal**: Regime + `k` selectable per single run via `Settings`, validated at startup; the run path
resolves the 004 member + frozen split via `load_member`; no regime branch beyond the `build_view` seam.

**Independent Test**: Run the same `(member, seed)` under all three regimes changing only config;
confirm identical held-fixed factors and that only the memory shown differs; an unknown regime fails fast.

- [X] T006 [US1] Add a scalar `regime: MemoryRegime` (default `recent_only`) and ensure single-run `k` to `Settings` in `src/ds_agent_loop/prompts.py`, with a field validator that rejects unknown/malformed regimes at startup (FR-002).
- [X] T007 [US1] In `src/ds_agent_loop/main.py`, wire the single-run path (`main`/`run_loop` entry) to read `Settings.regime`/`k` and pass them into `run_cell`; confirm the loop body has no regime-specific branch beyond the existing `memory.build_view` call (FR-001).
- [X] T008 [US1] In `src/ds_agent_loop/main.py`, resolve the member descriptor + frozen split via `benchmark.load_member` (content-hash asserted) in the run path and remove the on-disk `frozen_split` fallback from that path (keep it for offline tests only) so views are keyed to the 004 member (FR-004, research Decision 5).
- [X] T009 [US1] Accept a `--member <id> --seed <n>` invocation in the `ds-agent-loop` entrypoint (`src/ds_agent_loop/main.py` / `entrypoint/run.py`) that runs one member under the configured regime.
- [X] T010 [P] [US1] Test in `tests/test_memory.py`: all three regimes selectable from config produce runs whose only difference is the rendered memory; assert prompts/action-space/allowlist/budget/split/scoring identical (SC-001/002).
- [X] T011 [P] [US1] Test in `tests/test_memory.py`: an unknown regime value raises at `Settings` construction (fail-fast, FR-002).

**Checkpoint**: A member runs under any regime from config alone — independently demoable MVP.

---

## Phase 4: User Story 2 — Record the exact memory shown before every decision (Priority: P1)

**Goal**: Confirm/strengthen that every decision's exact view is persisted **before** the decision,
content-hashed, listing included ids, keyed to `(member, seed, regime, iteration)`, and linked from the record.

**Independent Test**: Run a member under one regime; for each iteration verify a persisted view exists,
is hashed, lists included ids, is correctly keyed, and the record's `memory_view_ref` matches.

- [X] T012 [US2] Verify/adjust `run_cell` in `src/ds_agent_loop/main.py` so `store.save_view` precedes record write and `record.memory_view_ref == view.content_hash` holds for member-keyed cells (FR-005/006); add the `config_fingerprint` stamp into `cell.repro` here at cell creation.
- [X] T013 [P] [US2] Test in `tests/test_loop.py`: after a member run, every iteration has a persisted `MemoryView` with non-empty `content_hash`, `included_record_ids`, correct `(cell_id, iteration)` key, and a matching `memory_view_ref` on the record (SC-003).
- [X] T014 [P] [US2] Test in `tests/test_loop.py`: the view is saved before the record (ordering) — assert no record exists for iteration `i` without its view (provenance-before-decision).

**Checkpoint**: Exact memory shown is provably captured and linked per decision.

---

## Phase 5: User Story 3 — Replay any decision's memory view and verify it (Priority: P2)

**Goal**: Deterministically rebuild any decision's view from persisted history and assert hash equality;
no LLM calls; loud mismatch.

**Independent Test**: For a completed run, replay every decision and confirm rebuilt hash == stored hash,
no LLM calls; a corrupted view fails loudly naming the iteration.

- [X] T015 [US3] Implement `provenance.replay_view(record, history_before, *, artifact=None)` in `src/ds_agent_loop/provenance.py` — rebuild via `memory.build_view` under the record's regime/`k`(+artifact), compare to `record.memory_view_ref`; return `ReplayMismatch | None` (FR-008/009).
- [X] T016 [US3] Implement `provenance.verify_cell(store, cell_id)` in `src/ds_agent_loop/provenance.py` — iterate records in order, supply history strictly before each and the artifact current at that iteration, aggregate into a `ReplayResult`; no LLM calls (FR-008, US3).
- [X] T017 [US3] Implement the `memory replay --cell <id>` / `--all` CLI branch in `provenance.main` (`src/ds_agent_loop/provenance.py`), exit non-zero + list mismatches on failure (FR-017, contracts/provenance-api.md).
- [X] T018 [P] [US3] Test in `tests/test_provenance.py`: `verify_cell` reports 100% hash match for a clean run across all three regimes, and performs no LLM calls (SC-004).
- [X] T019 [P] [US3] Test in `tests/test_provenance.py`: a tampered persisted `rendered_text`/hash makes `verify_cell` return `ok=False` identifying the offending iteration (FR-009, loud fail).
- [X] T020 [P] [US3] Test in `tests/test_provenance.py`: empty-history first decision and `k`>history cases replay byte-identically (FR-013, SC-006).

**Checkpoint**: Every recorded decision is provably replayable from persisted state.

---

## Phase 6: User Story 4 — Audit two regimes against each other (Priority: P2)

**Goal**: Prove two same-`(member, seed)` cells differ ONLY in memory via fingerprint equality; fail
loudly on contamination or invalid pairing.

**Independent Test**: Audit two regimes of one `(member, seed)`; confirm fingerprint equality and memory
as the differing dimension; audit fails when a held-fixed factor differs or members/seeds differ.

- [X] T021 [US4] Implement `provenance.audit_regimes(store, cell_id_a, cell_id_b)` in `src/ds_agent_loop/provenance.py` — gate on same `(member, seed)`; compare `config_fingerprint` (name first differing factor on mismatch); on success report regime/`k` difference and per-iteration view pairs; return `AuditResult` (FR-011, research Decision 3).
- [X] T022 [US4] Implement the `memory audit --cell-a <id> --cell-b <id>` CLI branch in `provenance.main` (`src/ds_agent_loop/provenance.py`), exit non-zero on contamination/invalid pair (FR-017).
- [X] T023 [P] [US4] Test in `tests/test_provenance.py`: two regimes over the same `(member, seed)` audit `ok=True` with equal fingerprint and the regime as `differing_dimension` (SC-005).
- [X] T024 [P] [US4] Test in `tests/test_provenance.py`: a held-fixed-factor difference (e.g. different budget/split) yields `ok=False` naming the contaminating factor (FR-011).
- [X] T025 [P] [US4] Test in `tests/test_provenance.py`: auditing cells of different members or seeds is rejected as "not a memory-only comparison" (FR-011 gate).

**Checkpoint**: "Memory is the only variable" is a checkable property, not an assumption.

---

## Phase 7: User Story 5 — Inspect and export memory provenance (Priority: P3)

**Goal**: Memory views + decision links inspectable in Postgres and exportable per cell to JSON/CSV that
round-trips byte-identically; schema is Alembic-managed (no new migration needed here).

**Independent Test**: Export a completed cell; confirm per-iteration views (text+ids+hash) and links
round-trip to byte-identical data; confirm the schema was created via Alembic.

- [X] T026 [US5] Verify `store.export` writes per-cell `memory_views.json` (text, `included_record_ids`, `content_hash`, key) and that `analysis.py` re-reads them; extend to include the `config_fingerprint` from `cell.repro` in the export index (`src/ds_agent_loop/store.py`, `src/ds_agent_loop/analysis.py`) (FR-015).
- [X] T027 [P] [US5] Test in `tests/test_provenance.py` (or `tests/test_analysis.py`): export → reload yields byte-identical memory views and decision links for a cell (SC-007).
- [X] T028 [P] [US5] Test/assertion confirming the `memory_views` schema is owned by the existing Alembic migrations and no operational `create_all`/ad-hoc DDL is added by this feature (FR-014, Principle IV).

**Checkpoint**: Provenance is portable and inspectable without DB access.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Invariants, docs, and the progress snapshot.

- [X] T029 [US1] Guard regime/`k` change on resume in `run_cell` (`src/ds_agent_loop/main.py`): if an existing cell's persisted regime/`k` differ from the requested ones, fail loudly (FR-012); test in `tests/test_loop.py`.
- [X] T030 [P] Run the full suite offline (`uv run pytest`) and the Postgres integration path (skipped without DB); confirm replay/audit make no LLM calls.
- [X] T031 [P] Update `README.md` with the `ds-agent-memory replay`/`audit` usage and regime-as-config selection (mirror `quickstart.md`).
- [X] T032 Refresh `notes/progress.html` (dark scheme per constitution v5.3.0): mark 005 implemented, summarize the verification layer, and set next step to 006.

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T005)** block everything.
- **US1 (T006–T011)** is the MVP and re-keys the run path; **US2 (T012–T014)** depends on US1's member-keyed run path.
- **US3 (T015–T020)** depends on Foundational + a member-keyed run producing views (US1/US2).
- **US4 (T021–T025)** depends on `config_fingerprint` (T005) and member-keyed cells (US1/US2); independent of US3.
- **US5 (T026–T028)** depends on persisted views (US1/US2); independent of US3/US4.
- **Polish (T029–T032)** last; T029 (resume guard) pairs with US1.

```
Setup → Foundational → US1 → US2 ─┬→ US3
                                  ├→ US4
                                  └→ US5 → Polish
```

## Parallel Execution Examples

- **Setup**: T003 ∥ (T001→T002).
- **Foundational**: T004 ∥ T005 (different files).
- **US1 tests**: T010 ∥ T011 after T006–T009.
- **US3**: implement T015→T016→T017, then T018 ∥ T019 ∥ T020.
- **US4**: implement T021→T022, then T023 ∥ T024 ∥ T025.
- **Cross-story**: once US1/US2 land, US3, US4, and US5 phases can proceed in parallel (distinct files: `provenance.py` tests vs `store.py`/`analysis.py`).

## Implementation Strategy

- **MVP = Phase 1–3 (US1)**: regime selectable as config over the 004 benchmark — immediately demoable.
- **Increment 2 = US2+US3**: provenance captured and *verified* replayable (the Principle IX payoff).
- **Increment 3 = US4**: the auditable controlled-variable guarantee (unblocks the 007 study).
- **Increment 4 = US5+Polish**: export, docs, progress snapshot.

## Notes

- No Alembic migration: the only new persisted value (`config_fingerprint`) lives in the existing
  `ExperimentCell.repro` JSONB; all view/record tables already exist.
- `memory.build_view` is unchanged — replay reuses it so "rebuilt" and "shown" are identical code.
- Replay and audit add **no LLM job** and consume the existing 003 `compaction.py` artifact opaquely
  (FR-016, clarification 2026-06-13).
