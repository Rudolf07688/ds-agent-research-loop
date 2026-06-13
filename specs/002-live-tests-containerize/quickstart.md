# Quickstart: Live Verification & Container Run (Vertex/Gemini + ADK)

**Feature**: `002-live-tests-containerize` | **Date**: 2026-06-13

Prerequisite: the re-platform (US1) is implemented — `google.genai` + minimal ADK replace
the OpenAI client, `Settings` carries the Vertex fields, deps updated, runtime on Python 3.13.

## 1. Configure Google Cloud auth (ADC)

```bash
gcloud auth application-default login
gcloud config set project research-se-gen-ai
```

Copy `.env.example` → `.env` only if you need to override defaults (project/location/model).
Do **not** put credentials in `.env`; ADC is discovered from the environment.

## 2. Offline tests still pass (hermetic, no network)

```bash
uv sync
uv run pytest        # uses a stubbed agent client — zero Vertex calls
```

## 3. Live verification (manual, one real run)

```bash
uv run python entrypoint/smoke_live.py
# or the full consumer:
uv run python entrypoint/run.py
```

Confirm: `state/seed_rows.json` + `state/data_spec.json` created by exactly one seed call;
the configured iterations run; `entrypoint/runs/run_<dt>/results.text` written;
`state/history.json` + `state/best_run.json` populated; a deliberately bad proposal is
rejected and the prior best retained. Re-running against existing valid `state/` skips the
seed call (resume).

## 4. Build & run the container

```bash
docker build -t ds-agent-loop .

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

Confirm results appear under `entrypoint/runs/` on the host after the container exits, and
that `docker run ... ds-agent-loop` with no credentials fails fast. Inspect the image
(`docker history` / `docker run --rm ds-agent-loop ls -a`) to confirm no `.env`, ADC, or
`state/`/`runs/` artifacts were baked in.

## Maps to success criteria

| Step | Success criteria |
|------|------------------|
| 2 | SC-001, SC-002 (offline behavior preserved) |
| 3 | SC-003, SC-004, SC-005, SC-006 (live round-trip, resume, rejection, fail-fast) |
| 4 | SC-007, SC-008 (container run + clean image), SC-009 (docs-only operability) |
