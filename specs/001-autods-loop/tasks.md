---
description: "Task list for LLM Autonomous Data Scientist (Toy) Loop"
---

# Tasks: LLM Autonomous Data Scientist (Toy) Loop

**Input**: Design documents from `/specs/001-autods-loop/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. The plan scopes pytest units for the safety-critical validation
paths and the loop logic (no LLM in the automated test loop).

**Organization**: Tasks are grouped by user story (US1–US5) for independent
implementation and testing. All Python is run via `uv run python ...` (Constitution
Principle VI); all paths are at the repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 (maps to spec.md user stories)
- Exact file paths are included in each task

## Path Conventions

Single flat project at repo root: modules `llm.py`, `data_gen.py`, `train.py`,
`history.py`, `prompts.py`, `main.py`; state files under `state/`; outputs under
`outputs/`; tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and structure

- [X] T001 Create the flat project structure (empty modules `llm.py`, `data_gen.py`, `train.py`, `history.py`, `prompts.py`, `main.py`; dirs `state/`, `outputs/`, `tests/`) per plan.md
- [X] T002 Initialize the uv project: create `pyproject.toml` (Python 3.11+) and add deps via `uv add` — scikit-learn, pandas, numpy, pydantic, pydantic-settings, python-dotenv, the LLM SDK, and pytest (dev); generate `uv.lock`
- [X] T003 [P] Create `.env.example` documenting LLM API key + model name variables
- [X] T004 [P] Create initial `README.md` with uv-based setup/run instructions (`uv sync`, `uv run python main.py`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every story needs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Define the structured entities as Pydantic models (DataSpec, DeliveryRecord, NextStepDecision; matching `contracts/seed_generation.schema.json` and `contracts/next_step.schema.json`) plus the prompt templates in `prompts.py` (Principle VIII)
- [X] T005a [P] Define the centralized `pydantic-settings` Settings object (RunConfig: n_iterations, patience, target_size, primary_metric, llm_model, llm_api_key) loading from `.env` in `prompts.py` or a small `config.py`-style block referenced by other modules (Principle VIII)
- [X] T006 Implement the async LLM client base + a generic `async` structured-JSON request helper (asyncio for the I/O-bound call) that validates responses into the Pydantic models (reads model/key from the Settings object) in `llm.py` (FR-018)
- [X] T007 [P] Define the model allowlist constant and the feature/target column constants in `train.py`

**Checkpoint**: Pydantic models, Settings, LLM helper, and allowlist exist — stories can begin

---

## Phase 3: User Story 1 - Bootstrap seed dataset and reusable data spec (Priority: P1) 🎯 MVP

**Goal**: On first run with no state, obtain a seed sample + reusable `data_spec` from one
LLM call and persist both; reuse existing state on later runs.

**Independent Test**: Run in an empty workspace → `state/seed_rows.json` and
`state/data_spec.json` are created; rerun → they are reused with no second LLM call.

### Tests for User Story 1

- [X] T008 [P] [US1] Unit test: seed/spec generation is skipped when valid `state/seed_rows.json` + `state/data_spec.json` already exist (no LLM call), in `tests/test_data_gen.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement the seed-generation call (request `seed_rows` + `data_spec` using the seed schema) in `llm.py`
- [X] T010 [US1] Validate seed-generation output against the schema and reject malformed/incomplete output in `llm.py`
- [X] T011 [US1] Implement seed bootstrap: persist `state/seed_rows.json` and `state/data_spec.json`, and skip generation when valid state already exists, in `data_gen.py`

**Checkpoint**: Seed bootstrap works and is resumable

---

## Phase 4: User Story 2 - Grow the dataset locally without additional LLM calls (Priority: P1)

**Goal**: Expand the dataset to a target size locally, deriving all rows from the saved
`data_spec`, with no LLM call and no spec regeneration.

**Independent Test**: From a saved `data_spec`, expand to a larger target size → larger
`dataset.csv` produced with no LLM call; all rows satisfy the spec.

### Tests for User Story 2

- [X] T012 [P] [US2] Unit test: expansion derives rows solely from the saved `data_spec` (no LLM call) and every row satisfies the spec's ranges/categories, in `tests/test_data_gen.py`

### Implementation for User Story 2

- [X] T013 [US2] Implement local row generation from the saved `data_spec` (features, rules, categories, noise_level) in `data_gen.py`
- [X] T014 [US2] Implement dataset expansion to a target size and persist `state/dataset.csv`, always anchored to the original saved spec (no regeneration), in `data_gen.py`

**Checkpoint**: Dataset grows locally and cheaply from the fixed spec

---

## Phase 5: User Story 3 - Train, evaluate, and track candidate models (Priority: P1)

**Goal**: Train one allowlisted regressor per iteration, score it via 5-fold CV (mean
RMSE), append the run to history, and update the best run on improvement.

**Independent Test**: Given a dataset and a chosen model, train + score it → a history
entry is appended and `best_run.json` updates only when RMSE improves.

### Tests for User Story 3

- [X] T015 [P] [US3] Unit test: model allowlist + hyperparameter validation rejects out-of-allowlist models and invalid hyperparameters before training, in `tests/test_train.py`
- [X] T016 [P] [US3] Unit test: history append records all required fields and best-run selection updates only on RMSE improvement, in `tests/test_history.py`

### Implementation for User Story 3

- [X] T017 [US3] Implement feature prep and estimator construction from an allowlisted model name + validated hyperparameters in `train.py`
- [X] T018 [US3] Implement hyperparameter validation that rejects invalid values before any training in `train.py`
- [X] T019 [US3] Implement 5-fold cross-validation scoring (fixed seed; mean RMSE primary, optional R²/MAE) in `train.py`
- [X] T020 [US3] Implement history append (iteration, dataset_size, model_name, hyperparameters, metrics, rationale, timestamp) writing to `state/history.json` in `history.py`
- [X] T021 [US3] Implement best-run tracking that updates `state/best_run.json` only when mean RMSE improves in `history.py`

**Checkpoint**: A single iteration can train, score, and be recorded end-to-end

---

## Phase 6: User Story 4 - Let the LLM propose the next experiment step (Priority: P2)

**Goal**: Ask the LLM for a constrained next-step decision from recorded results; validate
it; on rejection, skip and keep the prior model (never execute code).

**Independent Test**: Given a populated history, request a decision → returns one allowed
action with a rationale; an invalid/out-of-allowlist proposal is rejected and the loop
retains the prior model.

### Tests for User Story 4

- [X] T022 [P] [US4] Unit test: a rejected proposal (bad action/model/hyperparameters) is refused and the loop skips it while retaining the prior model (FR-016a), in `tests/test_loop.py`

### Implementation for User Story 4

- [X] T023 [US4] Implement the next-step call (reason over `state/history.json`, return a `NextStepDecision` via the next-step schema) in `llm.py`
- [X] T024 [US4] Implement decision validation (action enum, model on allowlist, hyperparameters valid; reject any non-conforming or code-bearing content, never execute it) in `train.py`
- [X] T025 [US4] Implement rejection handling: on an invalid decision, skip the proposal, retain the current/previous model, and record the rejection in history, in `history.py`

**Checkpoint**: The LLM can steer the experiment within safe, validated bounds

---

## Phase 7: User Story 5 - Run the full loop for N iterations with stop conditions (Priority: P2)

**Goal**: Orchestrate seed → expand → train/evaluate → next-step → record per iteration,
starting from the `LinearRegression` baseline, stopping at N or after k no-improvement
rounds.

**Independent Test**: Configure a small N, run end-to-end → each step runs per iteration;
loop stops at N or on the no-improvement condition; state reflects all iterations.

### Tests for User Story 5

- [X] T026 [P] [US5] Unit test: stop conditions — loop stops after N iterations and stops early after k consecutive non-improving rounds, in `tests/test_loop.py`

### Implementation for User Story 5

- [X] T027 [US5] Implement CLI argument parsing (`--iterations`, `--patience`, `--target-size`, `--metric`) and ensure `state/`/`outputs/` exist, with file-path constants, in `main.py`
- [X] T028 [US5] Implement the loop orchestration (seed-if-missing → expand → train/score → ask next-step → record), awaiting the async LLM calls (e.g. via `asyncio.run`) and using `LinearRegression` as the first-iteration baseline (FR-005a), in `main.py`
- [X] T029 [US5] Implement stop logic: terminate after N iterations or after `--patience` consecutive rounds without RMSE improvement, in `main.py`
- [X] T030 [US5] Write a human-readable `outputs/run_summary.txt` summarizing the run outcome in `main.py`

**Checkpoint**: A full `uv run python main.py` toy run completes and self-terminates

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validation, docs, and the user-facing progress channel

- [X] T031 [P] Finalize `README.md` and `.env.example` (uv workflow, run/inspect/test commands)
- [X] T032 Run quickstart validation end-to-end: `uv run python main.py` then `uv run pytest`, confirming success criteria SC-001…SC-007
- [X] T033 [P] Compile current progress into an HTML snapshot under `notes/` (Constitution Principle VII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phase 3–7)**: All depend on Foundational
  - Recommended order is priority order: US1 → US2 → US3 → US4 → US5
  - US5 (the orchestrator) integrates US1–US4 and should come last
- **Polish (Phase 8)**: Depends on the desired stories being complete

### User Story Dependencies

- **US1 (P1)**: After Foundational. Independent.
- **US2 (P1)**: After Foundational. Consumes the saved `data_spec` from US1 at runtime but is independently testable from any saved spec.
- **US3 (P1)**: After Foundational. Independently testable on any dataset.
- **US4 (P2)**: After Foundational. Reuses the allowlist/validation from US3 (`train.py`); test is independent via a fixture history.
- **US5 (P2)**: After Foundational. Orchestrates US1–US4; build last.

### Shared-File Notes (why some tasks are NOT [P])

- `llm.py`: T006 (foundational) → T009/T010 (US1) → T023 (US4) — sequence, same file.
- `train.py`: T007 (foundational) → T017/T018/T019 (US3) → T024 (US4) — sequence.
- `data_gen.py`: T011 (US1) → T013/T014 (US2) — sequence.
- `history.py`: T020/T021 (US3) → T025 (US4) — sequence.
- `main.py`: T027 → T028 → T029 → T030 (US5) — sequence.

### Within Each User Story

- Tests are written first and expected to FAIL before implementation.
- Models/data shaping before scoring; scoring before orchestration.

### Parallel Opportunities

- Setup: T003, T004 in parallel.
- Foundational: T005, T007 in parallel (T006 separate but parallel to both — different file).
- Test tasks across different test files (T008, T012, T015, T016, T022, T026) can be written in parallel.
- Polish: T031, T033 in parallel.

---

## Parallel Example: Foundational Phase

```bash
# Different files — safe to do together:
Task: "Define JSON schemas + prompts in prompts.py"        # T005
Task: "Implement LLM client base in llm.py"                # T006
Task: "Define model allowlist + column constants in train.py"  # T007
```

---

## Implementation Strategy

### MVP First

1. Phase 1 Setup → Phase 2 Foundational.
2. Phase 3 (US1) → STOP and validate: empty workspace bootstraps and persists seed +
   spec, and reuses them on rerun (SC-001, SC-007).

### Incremental Delivery

1. Setup + Foundational → ready.
2. US1 (bootstrap) → US2 (local expansion, SC-002) → US3 (train/score/track) → each
   independently testable.
3. US4 (LLM steering within safe bounds, SC-004) → US5 (full self-terminating loop,
   SC-003/SC-005).
4. Polish: quickstart validation + notes/ HTML snapshot.

### MVP Scope

User Story 1 alone (Phases 1–3) is the suggested MVP: it proves the LLM can bootstrap a
usable, reusable, resumable starting point.

---

## Notes

- All Python runs via `uv run python ...`; deps change only through `uv` (Principle VI).
- Commit messages MUST NOT include an AI co-author trailer (Constitution Development
  Workflow).
- On finishing a section or pausing, write an HTML progress snapshot to `notes/`
  (Principle VII) — T033 covers the milestone snapshot.
- [P] = different files, no incomplete-task dependencies; verify tests fail before
  implementing.
