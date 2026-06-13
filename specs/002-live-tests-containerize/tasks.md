---
description: "Task list for 002-live-tests-containerize"
---

# Tasks: Re-platform onto Google Vertex AI + Gemini (ADK), with Live Verification & Containerized Deployment

**Input**: Design documents from `/specs/002-live-tests-containerize/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/config-and-runtime.md, quickstart.md

**Tests**: The existing offline `pytest` suite is a hard requirement (FR-005 — must pass with zero network calls), so test-update tasks are included. No new TDD ceremony is added beyond keeping that suite green.

**Prerequisite already satisfied**: Constitution amended to v2.0.0 (permits minimal ADK), so FR-000 is met.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (re-platform), US2 (live verify), US3 (container)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Toolchain + dependency swap so the new backend can be installed

- [ ] T001 Pin runtime to Python 3.13 by changing `.python-version` from `3.14` to `3.13` (research Decision 1); leave `requires-python = ">=3.11"` in `pyproject.toml`
- [ ] T002 In `pyproject.toml`, remove the `openai` dependency and add `google-genai` and `google-adk` (research Decision 5)
- [ ] T003 Run `uv sync` to resolve/lock the new deps on Python 3.13 and confirm `uv.lock` updates cleanly (verify research Decision 1)

**Checkpoint**: Environment installs the Google SDK + ADK on a supported Python.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Centralized config + env surface that every story depends on

**⚠️ CRITICAL**: US1–US3 cannot proceed until the Settings/env surface reflects Vertex/Gemini

- [ ] T004 Modify `Settings` in `src/ds_agent_loop/prompts.py`: remove `llm_api_key`, `llm_base_url`, `llm_model`; add `google_cloud_project: str = "research-se-gen-ai"`, `google_cloud_location: str = "global"`, `gemini_model: str = "gemini-3.5-flash"`, `use_vertexai: bool = True` (data-model.md). Leave the run-parameter fields and all schemas/prompts in this file unchanged.
- [ ] T005 [P] Rewrite `.env.example`: drop `LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL`; document ADC auth and the overridable `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`/`GEMINI_MODEL`/`GOOGLE_GENAI_USE_VERTEXAI` vars (contracts/config-and-runtime.md). Never include credentials.

**Checkpoint**: Single source of truth points at Vertex/Gemini with the clarified defaults.

---

## Phase 3: User Story 1 - Re-platform the loop onto Google's Gemini stack (Priority: P1) 🎯 MVP

**Goal**: Both sanctioned LLM jobs run against Gemini on Vertex AI via `google.genai`, hosted by a minimal ADK agent, with the bounded contract (two schemas, allowlist, hyperparameter validation, rejection) preserved.

**Independent Test**: With a stubbed agent client, `uv run pytest` passes with no network calls; the loop still issues exactly its two structured calls, enforces the allowlist, and rejects out-of-allowlist/invalid proposals.

### Implementation for User Story 1

- [ ] T006 [US1] Rewrite `src/ds_agent_loop/llm.py`: replace `AsyncOpenAI` with a `google.genai` client in Vertex mode (`genai.Client(vertexai=True, project=…, location=…)` driven by `Settings`); keep the module's public functions `generate_seed(settings)` and `request_next_step(settings, *, history_json, allowlist, best_summary)` and the `LLMError` type with identical signatures (research Decision 2/3, data-model.md).
- [ ] T007 [US1] In `src/ds_agent_loop/llm.py`, implement a minimal ADK `LlmAgent` factory used by both calls: one agent with `output_schema=SeedGeneration`, one with `output_schema=NextStepDecision`, no tools/sub-agents, executed once via an in-memory runner; validate the structured result back through the existing Pydantic models (research Decision 3).
- [ ] T008 [US1] In `src/ds_agent_loop/llm.py`, map auth/availability failures to `LLMError` so a missing/invalid ADC or a model that can't honor the schema fails fast with a clear message (FR-009; replaces the old `build_client` API-key check).
- [ ] T009 [US1] Verify `src/ds_agent_loop/main.py`, `train.py`, `data_gen.py`, `history.py` need no changes (they call the preserved wrapper functions); make only adjustments required by the new `Settings` field names if any surface.
- [ ] T010 [US1] Update `tests/` (notably `tests/test_loop.py`) to stub the ADK/`google.genai` agent instead of the OpenAI client, asserting exactly two structured calls and the rejection/allowlist path, with zero network access (FR-005).
- [ ] T011 [US1] Run `uv run pytest` and confirm all offline units pass with no network calls (SC-001); confirm a bad-proposal test still rejects and retains the prior best model (SC-002 behavior).

**Checkpoint**: The loop is fully re-platformed and offline-verifiable; the OpenAI client is gone (FR-001).

---

## Phase 4: User Story 2 - Verify the loop against live Gemini on Vertex AI (Priority: P2)

**Goal**: One real Vertex AI round-trip proves the re-platformed loop end-to-end.

**Independent Test**: With valid ADC, a single command produces seed state, runs the iterations, and writes a results file; re-running against existing state skips the seed call.

### Implementation for User Story 2

- [ ] T012 [US2] Add `entrypoint/smoke_live.py`: a manual live-verification script (NOT under `tests/`, excluded from `pytest`) that performs one real run and asserts SC outcomes — seed files created by exactly one seed call, iterations complete, `entrypoint/runs/run_<dt>/results.text` written, `state/history.json` + `state/best_run.json` populated (FR-005, FR-010).
- [ ] T013 [US2] Perform the live run per `quickstart.md` (`gcloud auth application-default login`; `uv run python entrypoint/smoke_live.py`) and verify SC-003 (history+metrics+rationale, best ≤ baseline), SC-004 (exactly one seed round-trip; zero on resume), SC-005, and the fail-fast-without-credentials case (SC-006). Record results in `notes/`.

**Checkpoint**: Live round-trip against Vertex/Gemini confirmed; resume verified.

---

## Phase 5: User Story 3 - Run the loop as a portable container (Priority: P3)

**Goal**: A portable image runs the loop with credentials/config supplied at launch and artifacts persisted outside the container.

**Independent Test**: On a clean machine with only a container runtime, build the image and complete a run with results present in a mounted location after exit; no secrets/artifacts baked in.

### Implementation for User Story 3

- [ ] T014 [P] [US3] Add `.dockerignore` excluding `.venv/`, `.git/`, `state/`, `outputs/`, `entrypoint/runs/`, `__pycache__/`, `.pytest_cache/`, `.env`, and any ADC/key files (FR-014, research Decision 7)
- [ ] T015 [US3] Add `Dockerfile`: multi-stage on `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`; stage 1 copies `pyproject.toml`+`uv.lock` and runs `uv sync --frozen --no-dev`; stage 2 copies `src/`+`entrypoint/`, installs the package, creates `state/`/`outputs/`/`entrypoint/runs/`, sets `ENTRYPOINT ["uv","run","python","entrypoint/run.py"]` (FR-009/FR-013/FR-016, research Decision 7)
- [ ] T016 [US3] Build (`docker build -t ds-agent-loop .`) and run per `quickstart.md` with ADC mounted and `entrypoint/runs` volume-mounted; confirm results persist after exit (FR-011/FR-015, SC-007), the no-credentials run fails fast (FR-009), and image inspection shows no secrets/local artifacts (FR-014, SC-008)

**Checkpoint**: Container build-and-run validated end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T017 [P] Update `README.md`: replace OpenAI-compatible setup with Vertex/Gemini + ADK config, the live-verification steps, and the container build/run instructions (FR-017, SC-009)
- [ ] T018 [P] Write an HTML progress snapshot to `notes/` capturing the re-platform + containerization status (Constitution Principle VII)
- [ ] T019 Run the `quickstart.md` flow top-to-bottom as a final validation pass (offline tests → live verify → container)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **US1 (Phase 3)**: Depends on Foundational. This is the MVP and a hard prerequisite for US2/US3 (they need a working Gemini/Vertex loop).
- **US2 (Phase 4)**: Depends on US1 (needs the re-platformed loop to make a real call).
- **US3 (Phase 5)**: Depends on US1 (container runs the re-platformed loop); does not require US2 to be complete, but live-running the container effectively repeats US2's verification.
- **Polish (Phase 6)**: After the desired stories are complete.

### Within User Story 1

- T006 → T007 → T008 are sequential (same file `llm.py`).
- T009 after the wrapper is stable; T010 after T006–T008; T011 last.

### Parallel Opportunities

- T005 [P] can run alongside T004's review (different files).
- T014 [P] (.dockerignore) can be authored anytime; independent of code.
- T017 [P] and T018 [P] (README, notes) are independent files.
- Note: US2 and US3 both depend on US1, so the stories are mostly sequential here (unlike a typical fan-out) because each builds on the working Gemini loop.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup (Python 3.13, deps).
2. Phase 2: Foundational (Settings/env).
3. Phase 3: US1 re-platform.
4. **STOP and VALIDATE**: `uv run pytest` green, offline behavior preserved — this is the MVP (the loop now runs on Gemini/Vertex + ADK).

### Incremental Delivery

1. Setup + Foundational → backend installable & configured.
2. US1 → offline-green re-platform (MVP).
3. US2 → one live Vertex round-trip proven.
4. US3 → portable container.
5. Polish → docs + notes + full quickstart validation.

---

## Notes

- `entrypoint/config.py` needs **no change** — it extends `Settings` and never referenced the removed `LLM_*` fields.
- Schemas (`SEED_GENERATION_SCHEMA`, `NEXT_STEP_SCHEMA`) and all loop entities stay byte-for-byte unchanged (FR-003/FR-004).
- ADK `output_schema` disables tools/transfer — this is the mechanism that keeps Principle III (bounded agency) intact; do not add tools to the agents.
- Never commit/bake ADC or `.env`; credentials are run-time only.
- Verify exact `google-adk` symbol names / runner shape against the installed version during T007 (research open item).
