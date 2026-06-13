---

description: "Task list for 004 Benchmark Harness & Dataset Suite"
---

# Tasks: Benchmark Harness & Dataset Suite

**Input**: Design documents from `/specs/004-benchmark-harness/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution Principle XI requires tests for the deterministic machinery
(splits, hashing, versioning, persistence, export). Test tasks are first-class here.

**Organization**: Grouped by user story (US1–US5) for independent implementation and testing.

**Context**: Feature 003 already shipped the descriptor/loader/suite/loop layer in
`src/ds_agent_loop/benchmark.py`, `train.py`, `main.py`. This feature **extends** those modules
(stratified+hashed splits, Postgres materialization, versioning, export); it does not rewrite them.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5

## Path Conventions

Single `src`-layout research library: `src/ds_agent_loop/`, `alembic/versions/`, `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the toolchain and design contracts are loaded; no scaffolding needed (project exists).

- [X] T001 Verify `uv run pytest` and `uv run alembic current` run clean on branch `004-benchmark-harness` (baseline before changes)
- [X] T002 Re-read contracts in `specs/004-benchmark-harness/contracts/` (db-schema.md, benchmark-api.md) and confirm table/field names against existing `src/ds_agent_loop/store.py` Table defs

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence schema + typed entities that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Extend `DatasetDescriptor` in `src/ds_agent_loop/benchmark.py` with `provenance`, `budget`, `patience`, `action_space`, `model_allowlist` fields (data-model.md §DatasetDescriptor); populate them in `_descriptor_for`
- [X] T004 Add `FrozenSplit` and version-fingerprint helpers (`content_hash`, `member_fingerprint`) to `src/ds_agent_loop/benchmark.py` (data-model.md §FrozenSplit, §BenchmarkVersion); add `BenchmarkDriftError` and `SplitError` exceptions
- [X] T005 Define `benchmark_members` and `benchmark_splits` `Table` objects in `src/ds_agent_loop/store.py` per contracts/db-schema.md (SQLAlchemy Core, JSONB columns)
- [X] T006 Create Alembic migration `alembic/versions/0002_benchmark_members_and_splits.py` (down_revision `0001`) with `upgrade()`/`downgrade()` mirroring T005 (contracts/db-schema.md)
- [X] T007 Apply and verify the migration: `uv run alembic upgrade head` then `uv run alembic downgrade -1 && uv run alembic upgrade head` (idempotent, reversible)

**Checkpoint**: Schema + typed entities ready — user stories can begin.

---

## Phase 3: User Story 1 — Define & materialize a single versioned member (Priority: P1) 🎯 MVP

**Goal**: Declare one member, materialize it once, and load it by id with byte-identical data + fixed factors.

**Independent Test**: Materialize `delivery_time`, load by id in two separate processes, assert split rows, metric+direction, budget, action space, allowlist are byte-identical both times.

### Tests for User Story 1

- [X] T008 [P] [US1] Test descriptor validation in `tests/test_benchmark.py`: classification ⇒ classifier allowlist + higher-is-better metric; regression ⇒ regressor allowlist + lower-is-better; metric/task-type mismatch rejected
- [X] T009 [P] [US1] Test `content_hash` stability across processes and that an anchored-synthetic member generates rows with no LLM call in `tests/test_benchmark.py`

### Implementation for User Story 1

- [X] T010 [US1] Implement `materialize_suite(store, dataset_ids, *, version)` (single-member path) in `src/ds_agent_loop/benchmark.py`: build descriptor, compute split+hash+fingerprint, upsert into `benchmark_members`/`benchmark_splits` (contracts/benchmark-api.md)
- [X] T011 [US1] Implement store upsert/read helpers for members + splits in `src/ds_agent_loop/store.py` (idempotent on `(dataset_id, version)`)
- [X] T012 [US1] Implement `load_member(store, dataset_id, *, version)` in `src/ds_agent_loop/benchmark.py`: read persisted descriptor+split, regenerate rows, assert content hash matches (raise `BenchmarkDriftError` on mismatch)
- [X] T013 [US1] Add a `materialize` subcommand entry in `src/ds_agent_loop/benchmark.py` `__main__` / CLI (quickstart §2)

**Checkpoint**: One member is declarable, materializable, and byte-identically loadable (SC-001).

---

## Phase 4: User Story 2 — Mixed regression+classification suite (Priority: P2)

**Goal**: Assemble 4–6 members spanning both task types and both provenances, enumerable programmatically.

**Independent Test**: Materialize the full suite; assert 4–6 members, ≥1 regression + ≥1 classification, ≥1 synthetic + ≥1 curated-real, `delivery_time` present, each individually loadable per US1.

### Tests for User Story 2

- [X] T014 [P] [US2] Test suite composition in `tests/test_benchmark.py`: `suite()`/`DEFAULT_SUITE_IDS` yields 4–6 members covering both task types and both provenances incl. `delivery_time`
- [X] T015 [P] [US2] Test stratified classification split preserves all classes across train/val/test and no test-row leakage in `tests/test_benchmark.py`

### Implementation for User Story 2

- [X] T016 [US2] Make `frozen_split` stratified for classification (two-stage `train_test_split(stratify=y)` under `SPLIT_SEED`) and flag a member whose split drops a class (`SplitError`) in `src/ds_agent_loop/benchmark.py` (research.md Decision 2)
- [X] T017 [US2] Tag each loader's descriptor with `provenance` (`anchored_synthetic` for `delivery_time`, `curated_real` for sklearn datasets) and confirm default suite has the required mix in `src/ds_agent_loop/benchmark.py`
- [X] T018 [US2] Extend `materialize_suite` to materialize the whole suite and enumerate persisted members (`tests/test_benchmark_persistence.py` covers full-suite materialize→load)

**Checkpoint**: Full mixed suite materializes and every member loads independently (SC-002, SC-003).

---

## Phase 5: User Story 3 — Versioned benchmark with recorded changes (Priority: P2)

**Goal**: Single benchmark version on every member; any fixed-factor change without a version bump is rejected; old versions stay attributable.

**Independent Test**: Read version from a materialized suite; change a member's split policy; confirm rejection without a recorded version bump and that the new version coexists with the old.

### Tests for User Story 3

- [X] T019 [P] [US3] Test version-drift rejection in `tests/test_benchmark_persistence.py`: re-materializing under the same version with a changed fixed factor raises `BenchmarkDriftError`
- [X] T020 [P] [US3] Test version coexistence: materializing a new version leaves prior-version rows intact and attributable in `tests/test_benchmark_persistence.py`

### Implementation for User Story 3

- [X] T021 [US3] Implement `check_version_drift(store, descriptor, *, version)` in `src/ds_agent_loop/benchmark.py`: compare recomputed fingerprint to persisted; mismatch under existing version ⇒ raise (research.md Decision 3)
- [X] T022 [US3] Wire `check_version_drift` into `materialize_suite` upsert path so drift is caught before write; ensure rows keyed by `(dataset_id, benchmark_version)` so versions coexist

**Checkpoint**: Version is attached to every member; drift is rejected; old versions re-derivable (SC-005).

---

## Phase 6: User Story 4 — Run the existing loop against any member by id (Priority: P2)

**Goal**: The loop runs on any member by id using that member's allowlist, action space, direction-aware metric, and budget — no delivery-time-specific path.

**Independent Test**: Run the loop against one regression member and one classification member by id; confirm correct allowlist, frozen action space enforcement, direction-aware scoring, budget stop, and rejection of out-of-allowlist/action-space proposals.

### Tests for User Story 4

- [X] T023 [P] [US4] Integration test in `tests/test_loop.py`: stubbed-LLM run on a regression member (regressors only, lower-is-better, stops at budget) and a classification member (classifiers only, higher-is-better, out-of-allowlist proposal rejected before training)
- [X] T024 [P] [US4] Test the loop resolves its descriptor + frozen split from the materialized suite (not file-only) and records the stop reason in `tests/test_loop.py`

### Implementation for User Story 4

- [X] T025 [US4] Update `experiment.py` / `main.py` to resolve the descriptor + frozen split via `benchmark.load_member` (materialized suite) instead of `get_descriptor`+file split, keeping the descriptor-driven `run_cell` path unchanged (research.md Decision 6)
- [X] T026 [US4] Ensure the member's frozen `action_space` is enforced and the stop reason (budget `N` vs patience `k`) is recorded in the run record (FR-016) in `src/ds_agent_loop/main.py`

**Checkpoint**: Loop runs on any member by id with no delivery-time branch (SC-004).

---

## Phase 7: User Story 5 — Inspect & export the persisted benchmark (Priority: P3)

**Goal**: Inspect persisted members/splits in Postgres and export any member + its split rows to JSON/CSV that round-trips byte-identically.

**Independent Test**: Export a materialized member; confirm descriptor+rows reload byte-identical and the documented schema was created solely via Alembic.

### Tests for User Story 5

- [X] T027 [P] [US5] Test export round-trip in `tests/test_benchmark_persistence.py`: `export_member` → reload → byte-identical rows + matching content hash
- [X] T028 [P] [US5] Test re-materialization idempotency (no duplication) and loud failure on content-hash divergence in `tests/test_benchmark_persistence.py` (SC-007)

### Implementation for User Story 5

- [X] T029 [US5] Implement `export_member(store, dataset_id, out_dir, *, version)` writing `descriptor.json`+`rows.csv`+`split.json` under `out_dir/<version>/<dataset_id>/` in `src/ds_agent_loop/benchmark.py` (contracts/benchmark-api.md)
- [X] T030 [US5] Add an `export` subcommand to the `benchmark.py` CLI (quickstart §5) and a reload/verify helper that re-asserts the content hash

**Checkpoint**: Benchmark is inspectable and portably exportable (SC-006, SC-007).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T031 [P] Document the `benchmark_members`/`benchmark_splits` schema and the materialize/export workflow in `contracts/db-schema.md` cross-link + `README.md`/`notes/`
- [X] T032 Run `uv run pytest` (offline) and confirm the Postgres-backed integration tests pass under `docker compose up` end-to-end (Principle X)
- [X] T033 Run `notes/` HTML progress snapshot update using the canonical color scheme (Principle VII) and walk through `quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS all user stories (T003–T007).
- **User Stories (Phase 3–7)**: all depend on Foundational. US1 is the MVP and should land first; US2/US3/US4 build on US1's materialize/load; US5 consumes US1–US3 artifacts.
- **Polish (Phase 8)**: depends on all desired stories.

### User Story Dependencies

- **US1 (P1)**: after Foundational. Independent MVP.
- **US2 (P2)**: builds on US1 (per-member materialize/load); adds suite + stratification.
- **US3 (P2)**: builds on US1/US2 (needs persisted members to detect drift).
- **US4 (P2)**: needs US1 (load_member) and US2 (suite); independently testable via stub LLM.
- **US5 (P3)**: consumes persisted artifacts of US1–US3.

### Within Each User Story

- Tests written first and FAIL before implementation (Principle XI / TDD).
- Entities/helpers before persistence; persistence before CLI; core before integration.

### Parallel Opportunities

- T008/T009, T014/T015, T019/T020, T023/T024, T027/T028 (test pairs) are [P].
- Foundational T003 and T005 touch different files (benchmark.py vs store.py) and can overlap; T004 depends on T003, T006 depends on T005.

---

## Parallel Example: User Story 1

```bash
# Tests first (parallel):
Task: "Test descriptor validation by task type in tests/test_benchmark.py"
Task: "Test content_hash stability + no-LLM synthetic gen in tests/test_benchmark.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (schema + entities) → 3. Phase 3 US1 →
4. STOP & VALIDATE: materialize+load `delivery_time` byte-identical → MVP.

### Incremental Delivery

US1 (single member) → US2 (full mixed suite) → US3 (versioning) → US4 (loop on any member) →
US5 (inspect/export). Each adds value without breaking the prior increment.

---

## Notes

- [P] = different files, no dependencies.
- The loop path (`main.run_cell`, `train.score_on_split`) is already generic — US4 is mostly wiring resolution through `load_member`, not rewriting the loop.
- Commit after each task or logical group; the repo's git hooks offer commits at phase boundaries.
- Schema changes ONLY via Alembic (no operational `create_all`) — Principle IV.
