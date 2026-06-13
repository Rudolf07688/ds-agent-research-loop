# Start Here — 002 (live tests + containerization)

Picks up after the first spec phase (`001-autods-loop`) was implemented, restructured
into a publishable library, and committed. Branch: `001-autods-loop`.

## What exists now

The **LLM Autonomous Data Scientist (Toy) Loop** is implemented, tested (offline), and
packaged. All 33 spec tasks (T001–T033) are done; the offline pytest suite (20 tests)
passes.

### Layout
```text
src/ds_agent_loop/   # the publishable library package
  __init__.py        # public API: run_loop, Settings
  prompts.py         # Pydantic entities + single pydantic-settings Settings + 2 JSON schemas + prompts
  llm.py             # async OpenAI-compatible client; schema-constrained, Pydantic-validated calls
  data_gen.py        # seed bootstrap (resumable) + local expansion anchored to saved spec
  train.py           # model allowlist, hyperparameter/decision validation, 5-fold CV scoring
  history.py         # append-only history, best-run tracking, rejection recording
  main.py            # CLI + orchestration (seed -> expand -> score -> next-step -> record)
entrypoint/          # deployable consumer (imports FROM the library, never the reverse)
  run.py             # pulls run_loop; writes entrypoint/runs/run_<dt>/results.text
  config.py          # RunConfig(Settings): fixed 5 iterations, per-run isolated state
tests/               # pytest units against the installed package
state/ outputs/ notes/ entrypoint/runs/   # runtime artifacts (gitignored)
```

### How to run / test
```bash
uv sync                                   # builds + installs ds-agent-loop (editable)
uv run pytest                             # 20 offline units (no LLM)
uv run ds-agent-loop --iterations 5       # console script
uv run python -m ds_agent_loop.main       # equivalent module form
uv run python entrypoint/run.py           # entrypoint -> entrypoint/runs/run_<dt>/results.text
```
> Run Python only via `uv` (Constitution Principle VI). Never `python3`/`pip` directly.

## Key context & decisions from this session

- **Packaging (Constitution v1.3.0):** the flat root modules were moved into
  `src/ds_agent_loop/` and intra-package imports made relative. `pyproject.toml` gained
  the `uv_build` backend + a `ds-agent-loop` console script (`ds_agent_loop.main:main`).
  Principle I was amended (MINOR) to bless the `src` package + thin `entrypoint/`
  consumer; the single-purpose-module decomposition and no-frameworks rules still hold.
- **Architecture intent:** the `src` package is the *library* you'd publish to an
  artifact store; `entrypoint/` is the *consumer* you'd bake into a container. Keep the
  dependency one-way (entrypoint imports library, never the reverse).
- **Settings lives in `prompts.py`** (the one `pydantic-settings` object); `entrypoint/`
  extends it via `RunConfig`. No core `config.py` (the only `config.py` is the
  consumer's, in `entrypoint/`).
- **Safety boundary (Principles II/III):** LLM emits only schema-constrained JSON; models
  restricted to an allowlist; hyperparameters validated before training (via
  scikit-learn `_validate_params()` since 1.9 checks values at fit time); invalid/
  code-bearing proposals are rejected and the prior model retained.
- **Two LLM calls only:** seed-generation + next-step. Dataset expansion is local
  (token cost independent of dataset size).
- **State is resumable:** valid `state/seed_rows.json` + `state/data_spec.json` skip the
  seed call. The entrypoint isolates state per run (so each run re-seeds).
- **Commits MUST NOT include an AI co-author trailer** (Constitution Development Workflow).
- **Recent commits:** `1f08bb6` constitution v1.3.0 · `074a82e` src-layout restructure ·
  `ded6f55` entrypoint runner · `9d712fd` library implementation.
- **Not yet done:** a real end-to-end run with a live LLM (all e2e validation so far used
  a stubbed LLM).

## Next steps

### 1. Live tests (real LLM round-trip)
The seed-generation call is the first thing that needs a live provider; the loop only
catches `LLMError` around the next-step call, so a missing key fails fast at seeding.

- [ ] Create `.env` from `.env.example` with `LLM_API_KEY` + `LLM_MODEL` (an
      OpenAI-compatible model that supports JSON-schema structured output; set
      `LLM_BASE_URL` for a non-OpenAI endpoint).
- [ ] `uv run python entrypoint/run.py` → confirm one seed call creates
      `state/seed_rows.json` + `state/data_spec.json`, the loop runs 5 iterations, and
      `entrypoint/runs/run_<dt>/results.text` is written.
- [ ] Verify the constitution success criteria against real output: SC-001 (seed files),
      SC-003 (history + best_run), SC-004 (bad proposal rejected, not run), SC-005 (best
      RMSE ≤ baseline), SC-006/007 (resume without re-seeding from `state/`).
- [ ] Sanity-check the `data_spec` rules the model returns and the rejection path against
      a deliberately bad proposal (manual/log inspection — LLM calls stay out of the
      automated pytest loop by design).
- [ ] Optional: add a thin live smoke-test script under `entrypoint/` (kept out of the
      offline pytest run) for repeatable manual verification.

### 2. Containerize (Dockerfile)
Goal: a small image with the library installed and the entrypoint as the command —
mirrors the "publish library + deploy consumer" model.

- [ ] Add a `Dockerfile` (uv-based, multi-stage). Sketch:
  - Base on `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` (or pin to the project's
    Python; `.python-version` is 3.14 — confirm an available uv base or relax).
  - Copy `pyproject.toml` + `uv.lock` first; `uv sync --frozen --no-dev` for cached deps.
  - Copy `src/` + `entrypoint/`; install the package.
  - Create `state/`, `outputs/`, `entrypoint/runs/` (or mount as volumes).
  - `ENTRYPOINT ["uv", "run", "python", "entrypoint/run.py"]` (or the `ds-agent-loop`
    console script).
- [ ] Add `.dockerignore` (`.venv/`, `.git/`, `state/`, `outputs/`, `entrypoint/runs/`,
      `__pycache__/`, `.pytest_cache/`, `.env`). **Never** bake `.env`/secrets into the
      image — pass `LLM_API_KEY`/`LLM_MODEL` at runtime (`-e` / secrets).
- [ ] Decide artifact persistence: mount `state/` and `entrypoint/runs/` as volumes so
      results survive container exit and the run is resumable.
- [ ] Build + run:
      `docker build -t ds-agent-loop .` then
      `docker run --rm -e LLM_API_KEY -e LLM_MODEL -v "$PWD/entrypoint/runs:/app/entrypoint/runs" ds-agent-loop`.
- [ ] (Later) publish the wheel to an artifact store and slim the image to install the
      library from there instead of copying `src/` — the end-state the architecture is
      built for.

## Watch-outs
- Strict OpenAI structured-output mode rejects open objects; the next-step schema uses
  `additionalProperties: true` for `hyperparameters`, so the client uses
  `strict: false`. If you swap providers, re-verify JSON-schema support.
- `.python-version` pins 3.14; `requires-python` is `>=3.11`. Pick a Docker base that
  matches (or relax the pin) to avoid a build-time Python mismatch.
- Each entrypoint run re-seeds (isolated state) → one seed LLM call per run. For a
  shared/resumable run, point `state_dir` at the repo `state/` (set `isolate_state=False`).
