# Contract: Configuration & Runtime Surface

**Feature**: `002-live-tests-containerize`

The library is consumed via a console script / module and (now) a container. These are the
externally observable contracts this feature changes. The two LLM JSON schemas
(`SEED_GENERATION_SCHEMA`, `NEXT_STEP_SCHEMA`) are **unchanged** and live in
`src/ds_agent_loop/prompts.py` — they remain the LLM-interaction contract.

## Environment / configuration contract

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| ADC (via `GOOGLE_APPLICATION_CREDENTIALS` file, `gcloud` ADC, or workload identity) | **Yes** | — | Vertex AI authentication. Never committed/baked in. |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `TRUE` | Forces `google.genai` into Vertex AI mode. |
| `GOOGLE_CLOUD_PROJECT` | No | `research-se-gen-ai` | Target GCP project. |
| `GOOGLE_CLOUD_LOCATION` | No | `global` | Vertex location/region. |
| `GEMINI_MODEL` | No | `gemini-3.5-flash` | Gemini model for both calls. |
| `N_ITERATIONS` | No | `10` | Loop iteration cap. |
| `PATIENCE` | No | `3` | No-improvement stop. |
| `TARGET_SIZE` | No | `500` | Expanded dataset size. |
| `PRIMARY_METRIC` | No | `rmse` | Acceptance metric. |

- **Removed** (no longer recognized): `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`.
- Failure mode: missing/invalid ADC → fail fast at the first model call with a clear,
  actionable message (`LLMError`); no silent or partial success (FR-009, SC-006).

## CLI / entry contract (unchanged behavior)

- `uv run ds-agent-loop [--iterations N] …` — console script.
- `uv run python -m ds_agent_loop.main` — module form.
- `uv run python entrypoint/run.py` — consumer; writes `entrypoint/runs/run_<dt>/results.text`.
- New, manual, NOT in `pytest`: `uv run python entrypoint/smoke_live.py` — one real Vertex
  run asserting the success criteria.

## Container run contract

**Build**: `docker build -t ds-agent-loop .`

**Run** (artifacts persisted, credentials mounted, nothing baked in):

```bash
docker run --rm \
  -e GOOGLE_GENAI_USE_VERTEXAI=TRUE \
  -e GOOGLE_CLOUD_PROJECT=research-se-gen-ai \
  -e GOOGLE_CLOUD_LOCATION=global \
  -e GEMINI_MODEL=gemini-3.5-flash \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc/key.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/adc/key.json:ro" \
  -v "$PWD/entrypoint/runs:/app/entrypoint/runs" \
  ds-agent-loop
```

**Guarantees**:
- Default command runs the loop (FR-009).
- No credentials or local runtime artifacts in the image — verifiable by image inspection
  (FR-014, SC-008); enforced via `.dockerignore`.
- Run results persist in the mounted location after the container exits (FR-011, FR-015).
- Mounting `state/` as well makes the run resumable across container runs (FR-007 resume,
  Principle IV); without it, each run re-seeds in isolated state.
- Missing credentials → fail fast, no partial run (container exits non-zero with a clear
  message) (FR-009).
