# Phase 0 Research: Gemini/Vertex + ADK Re-platform, Live Verification, Containerization

**Feature**: `002-live-tests-containerize` | **Date**: 2026-06-13

This resolves the two items the spec deferred to planning (Python-version reconciliation,
`google.genai` ↔ ADK boundary) plus the supporting technology choices.

## Decision 1 — Runtime Python version

**Decision**: Pin the runtime to **Python 3.13** for both local dev and the container.
Update `.python-version` from `3.14` → `3.13`; keep `requires-python = ">=3.11"`.

**Rationale**: `google-adk` pulls in the gRPC/protobuf stack (`grpcio`, `protobuf`,
`google-api-core`) transitively. Python 3.14 is too new to guarantee prebuilt wheels for
that whole chain; a missing wheel forces a source build (or fails) inside the slim uv
Docker base. 3.13 is mature, has full wheel coverage for `google-genai`/`google-adk` and
scikit-learn/pandas/numpy, and matches an available `ghcr.io/astral-sh/uv:python3.13-*`
base — eliminating the build-time mismatch the notes warned about.

**Alternatives considered**:
- *Keep 3.14*: highest risk of missing/late wheels for the gRPC stack; rejected.
- *Drop to 3.11/3.12*: works, but 3.13 is the newest fully-supported version, so no reason
  to go older.

**Verify at implementation**: `uv sync` resolves cleanly on 3.13 and the chosen uv Docker
base tag exists.

## Decision 2 — Model backend: `google.genai` in Vertex AI mode

**Decision**: Use the **`google-genai`** SDK (`google.genai`) in **Vertex AI mode**:
`genai.Client(vertexai=True, project=<project>, location=<location>)`, or equivalently the
env switch `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`.
Authentication is **Application Default Credentials (ADC)** — no API key.

**Rationale**: Matches the operator requirement (Vertex AI, not the Developer API) and the
ADC clarification. Vertex mode discovers ADC automatically via the standard Google auth
chain, so the same code path works locally (`gcloud auth application-default login`) and in
the container (mounted ADC file via `GOOGLE_APPLICATION_CREDENTIALS`, or workload identity).

**Alternatives considered**:
- *Developer API (`api_key=`)*: simplest, but explicitly out of scope (not Vertex). Rejected.

## Decision 3 — ADK boundary: minimal `LlmAgent` with `output_schema`

**Decision**: Host each of the two sanctioned calls in a minimal **`google-adk`
`LlmAgent`** configured with a Pydantic `output_schema` (structured output), executed
through an `InMemoryRunner` / in-memory session. One agent for seed-generation
(`output_schema=SeedGeneration`), one for next-step (`output_schema=NextStepDecision`).
No tools, no sub-agents, no multi-turn planning.

**Rationale**:
- Setting `output_schema` on an `LlmAgent` forces structured JSON validated against the
  schema **and disables tool/transfer use** — which is exactly the bounded-agency posture
  the constitution (Principles II & III) demands. The framework itself enforces "no tools,"
  reinforcing the safety boundary rather than working around it.
- ADK drives `google.genai` underneath and honors Vertex via the same env switches, so the
  backend decision (Decision 2) and the agent layer compose without a second client.
- Keeps ADK use to the literal minimum the amended constitution permits (host two calls).

**Alternatives considered**:
- *Call `google.genai` directly, skip ADK*: simpler and constitution-compatible, but the
  operator explicitly requires ADK "for the agent." Rejected per requirement.
- *ADK with function-calling tools to run training*: would breach Principle III
  (bounded agency). Rejected outright.

**Verify at implementation**: confirm the installed `google-adk` exposes `LlmAgent`
+ `output_schema` + an in-memory runner, and that structured output round-trips into the
existing `SeedGeneration` / `NextStepDecision` models. The async helper keeps today's
`generate_seed(settings)` / `request_next_step(...)` signatures so `main.py` and tests are
untouched.

## Decision 4 — Settings & env surface

**Decision**: In the single `Settings` object, **remove** `llm_api_key`, `llm_base_url`,
`llm_model`; **add** `google_cloud_project` (default `research-se-gen-ai`),
`google_cloud_location` (default `global`), `gemini_model` (default `gemini-3.5-flash`).
ADC is supplied by the environment, not stored as a settings field. Rewrite `.env.example`
accordingly. Run-parameter fields (`n_iterations`, `patience`, `target_size`,
`primary_metric`) are unchanged.

**Rationale**: Honors the clarified defaults (only ADC mandatory; project/location/model
overridable) and keeps a single source of truth (Principle VIII). Dropping the OpenAI
fields reflects the "remove entirely" decision (no provider toggle).

## Decision 5 — Dependencies

**Decision**: In `pyproject.toml`, **remove** `openai`; **add** `google-genai` and
`google-adk`. Keep scikit-learn/pandas/numpy/pydantic/pydantic-settings/python-dotenv.

**Rationale**: Sole backend is Vertex/Gemini via ADK; the OpenAI dep is now dead weight and
its removal is part of FR-001. `python-dotenv` stays (pydantic-settings `.env` loading).

## Decision 6 — Live verification harness

**Decision**: Add a thin, manually-run smoke script under `entrypoint/` (e.g.
`entrypoint/smoke_live.py`) that performs one real run and asserts the SC outcomes (seed
files created, iterations completed, results file written, history/best_run present). It is
**excluded from `pytest`** (not under `tests/`, and `testpaths=["tests"]` already scopes the
offline suite). The offline suite keeps using a stubbed agent client — no network.

**Rationale**: Satisfies FR-005/FR-010 (repeatable live check kept out of the hermetic
offline suite) without polluting CI or incurring token cost on every `pytest`.

## Decision 7 — Container design

**Decision**: Multi-stage Dockerfile on `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`.
Stage 1: copy `pyproject.toml` + `uv.lock`, `uv sync --frozen --no-dev` (cached deps).
Stage 2: copy `src/` + `entrypoint/`, install the package; create `state/`, `outputs/`,
`entrypoint/runs/`; `ENTRYPOINT ["uv","run","python","entrypoint/run.py"]`. Add
`.dockerignore` excluding `.venv/`, `.git/`, `state/`, `outputs/`, `entrypoint/runs/`,
`__pycache__/`, `.pytest_cache/`, `.env`, and any ADC/key files. Credentials and config are
passed at run time (`-e GOOGLE_CLOUD_PROJECT=…`, `-e GOOGLE_GENAI_USE_VERTEXAI=TRUE`,
mounted ADC via `-v` + `-e GOOGLE_APPLICATION_CREDENTIALS`); artifacts persisted via
`-v "$PWD/entrypoint/runs:/app/entrypoint/runs"` (and `state/` if a shared resumable run is
wanted).

**Rationale**: Mirrors the "publish library + deploy consumer" model (FR-009/FR-013–016),
keeps secrets and local artifacts out of the image (FR-014, SC-008), and persists results
across container exit (FR-011/FR-015). 3.13 base aligns with Decision 1.

**Alternatives considered**:
- *Single-stage build*: larger image, no dep-layer caching. Rejected for the multi-stage.
- *Bake ADC into the image*: violates FR-014/secret rules. Rejected outright.

## Open items deferred to tasks (not blocking)

- Exact `google-adk` symbol names / runner call shape — verify against the installed
  version during T-implementation (Decision 3).
- Whether `location=global` is accepted for `gemini-3.5-flash` in the target project —
  confirmed at first live run; overridable per Decision 4 if a regional endpoint is needed.
