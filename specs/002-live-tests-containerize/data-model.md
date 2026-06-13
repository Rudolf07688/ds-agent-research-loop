# Phase 1 Data Model: Re-platform onto Vertex/Gemini + ADK

**Feature**: `002-live-tests-containerize` | **Date**: 2026-06-13

This feature is primarily a backend/packaging change. The loop's structured entities
(`DeliveryRecord`, `DataSpec`, `SeedGeneration`, `NextAction`, `NextStepDecision`,
`RunRecord`) and the two JSON schemas (`SEED_GENERATION_SCHEMA`, `NEXT_STEP_SCHEMA`) are
**unchanged** — preserving them is an explicit requirement (FR-003, FR-004). The only data
change is the centralized `Settings` object.

## Modified: `Settings` (pydantic-settings, in `prompts.py`)

The single source of truth for runtime config. The OpenAI fields are removed; Vertex/Gemini
fields are added with the clarified defaults. ADC is supplied by the environment and is NOT
a settings field.

| Field | Before | After | Env var | Notes |
|-------|--------|-------|---------|-------|
| `llm_api_key` | `str = ""` | **removed** | — | OpenAI client deleted (FR-001) |
| `llm_base_url` | `str \| None` | **removed** | — | — |
| `llm_model` | `str = "gpt-4o-mini"` | **removed** | — | replaced by `gemini_model` |
| `google_cloud_project` | — | `str = "research-se-gen-ai"` | `GOOGLE_CLOUD_PROJECT` | overridable (FR-006) |
| `google_cloud_location` | — | `str = "global"` | `GOOGLE_CLOUD_LOCATION` | overridable |
| `gemini_model` | — | `str = "gemini-3.5-flash"` | `GEMINI_MODEL` | overridable |
| `use_vertexai` | — | `bool = True` | `GOOGLE_GENAI_USE_VERTEXAI` | forces Vertex mode |
| `n_iterations` | `int = 10` | unchanged | `N_ITERATIONS` | — |
| `patience` | `int = 3` | unchanged | `PATIENCE` | — |
| `target_size` | `int = 500` | unchanged | `TARGET_SIZE` | — |
| `primary_metric` | `str = "rmse"` | unchanged | `PRIMARY_METRIC` | — |

**Validation rules**:
- Only ADC credentials are mandatory at run time; all three Vertex fields have defaults.
- A run with no resolvable ADC MUST fail fast at the first model call with a clear message
  (FR-009) — surfaced as `LLMError` from the wrapper, not a silent partial run.

**Auth (not a field)**: ADC is discovered via the standard Google chain
(`GOOGLE_APPLICATION_CREDENTIALS` file, `gcloud` ADC, or workload identity). It is never
persisted in the repo or image (FR-007, FR-014).

## Unchanged entities (preserved by FR-003/FR-004)

- `DeliveryRecord`, `DataSpec`, `SeedGeneration` — seed-generation output shape.
- `NextAction` (enum: keep_model | tune_hyperparameters | switch_model | expand_dataset |
  stop), `NextStepDecision` — next-step output shape.
- `RunRecord` — history row.
- On-disk state files under `state/` (`data_spec.json`, `seed_rows.json`, `dataset.csv`,
  `history.json`, `best_run.json`) — formats and resume semantics unchanged (Principle IV).

## Agent objects (new, transient — not persisted)

The minimal ADK agents are runtime objects, not durable state:

- **Seed agent**: `LlmAgent(model=gemini_model, output_schema=SeedGeneration, …)` — one call,
  no tools.
- **Next-step agent**: `LlmAgent(model=gemini_model, output_schema=NextStepDecision, …)` —
  one call, no tools.

Both are constructed from `Settings`, executed once per use through an in-memory runner, and
discarded. They carry no state across iterations beyond what the loop already persists to
`state/`.
