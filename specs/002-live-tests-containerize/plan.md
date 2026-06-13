# Implementation Plan: Re-platform onto Google Vertex AI + Gemini (ADK), with Live Verification & Containerized Deployment

**Branch**: `002-live-tests-containerize` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-live-tests-containerize/spec.md`

## Summary

Replace the loop's OpenAI-compatible LLM client with **Google Gemini on Vertex AI**
accessed via the **`google.genai`** SDK and hosted by a **minimal Google ADK agent** (one
agent per sanctioned call, structured output, no tools), preserving the two-schema contract,
model allowlist, hyperparameter validation, rejection behavior, and resumable state. Then
prove the re-platformed loop with a **manual live verification** run against Vertex AI, and
package it as a **portable container** that takes credentials/config at run time and
persists run artifacts to a mounted location — with no secrets or local artifacts baked in.
Auth is **Application Default Credentials (ADC)**; defaults are project `research-se-gen-ai`,
location `global`, model `gemini-3.5-flash` (all overridable). See [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.13 (pin `.python-version` 3.14 → 3.13; `requires-python >=3.11`). See research Decision 1.

**Primary Dependencies**: `google-genai`, `google-adk` (replacing `openai`); scikit-learn, pandas, numpy, pydantic, pydantic-settings, python-dotenv (unchanged).

**Storage**: Plain files under `state/` (`data_spec.json`, `seed_rows.json`, `dataset.csv`, `history.json`, `best_run.json`); run output under `entrypoint/runs/`. Formats unchanged.

**Testing**: `pytest` (offline, hermetic, stubbed agent client — zero network). Live verification is a separate manual script under `entrypoint/`, excluded from `pytest`.

**Target Platform**: Local (uv) and a Linux container (`ghcr.io/astral-sh/uv:python3.13-bookworm-slim`).

**Project Type**: Single `src`-layout library (`src/ds_agent_loop/`) + thin consumer (`entrypoint/`).

**Performance Goals**: Toy scope — token cost stays independent of dataset size (expansion is local); exactly two LLM calls' worth of round-trips per fresh run path (one seed + per-iteration next-step).

**Constraints**: Bounded agency (no tools/code execution via ADK); two sanctioned schemas only; ADC never committed/baked in; offline suite makes no network calls.

**Scale/Scope**: Single operator, single full run (fixed iteration count) validates the round-trip; no concurrency/load goals.

## Constitution Check

*GATE: evaluated against constitution v2.0.0.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity & Readability First | ✅ Pass | Single minimal ADK agent is now permitted (v2.0.0); no extra modules, no new indirection, OpenAI client removed (net simplification). `entrypoint/smoke_live.py` is a thin consumer-side script. |
| II. Constrained LLM Contracts (two schemas) | ✅ Pass | Same two schemas; ADK `output_schema` enforces structured JSON; no third job added. |
| III. Bounded Agency (no code exec) | ✅ Pass | `output_schema` on `LlmAgent` disables tools/transfer — framework-enforced no-tools; allowlist + hyperparameter validation + rejection path preserved. |
| IV. Inspectable & Reproducible State | ✅ Pass | State files and resume semantics unchanged; container mounts `state/`/`runs/`. |
| V. Anchored Synthetic Data Generation | ✅ Pass | Local expansion unchanged; token cost independent of dataset size. |
| VI. uv-Managed Python Environment | ✅ Pass | All runs via `uv run …`; deps changed only via `uv`; Docker base is uv-based. |
| VII. Progress via notes/ | ✅ Pass | HTML progress snapshot to be written at milestone/pause. |
| VIII. Typed Models & Centralized Settings | ✅ Pass | Single `Settings` object retained (Vertex fields swapped in); outputs validated via existing Pydantic models. |

**Result**: PASS — no violations. FR-000 prerequisite (constitution amendment) satisfied by
v2.0.0. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-live-tests-containerize/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions (Python 3.13, genai/Vertex, ADK boundary, deps, container)
├── data-model.md        # Phase 1 — Settings change; unchanged entities
├── quickstart.md        # Phase 1 — live verification + container run
├── contracts/
│   └── config-and-runtime.md   # env/config + container run + CLI contracts
├── checklists/
│   └── requirements.md  # spec quality checklist
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
src/ds_agent_loop/
├── __init__.py          # public API (run_loop, Settings) — unchanged surface
├── prompts.py           # MODIFY: Settings (drop LLM_*, add Vertex/Gemini fields); schemas/prompts unchanged
├── llm.py               # REWRITE: google.genai (Vertex mode) + minimal ADK LlmAgent per call;
│                        #          keep generate_seed()/request_next_step() signatures + LLMError
├── data_gen.py          # unchanged
├── train.py             # unchanged (allowlist + hyperparameter validation preserved)
├── history.py           # unchanged
└── main.py              # unchanged orchestration (uses the same wrapper functions)

entrypoint/
├── run.py               # unchanged consumer
├── config.py            # MODIFY if it references removed LLM_* fields
└── smoke_live.py        # NEW: manual live verification (excluded from pytest)

tests/                   # MODIFY: stub the ADK/genai agent instead of the OpenAI client; no network
Dockerfile               # NEW: multi-stage, uv python3.13 base, entrypoint runs the loop
.dockerignore            # NEW: exclude .venv/.git/state/outputs/runs/__pycache__/.pytest_cache/.env/ADC
.python-version          # MODIFY: 3.14 → 3.13
pyproject.toml           # MODIFY: remove openai; add google-genai, google-adk
.env.example             # REWRITE: Vertex/Gemini vars; remove LLM_* vars
README.md                # MODIFY: Vertex/Gemini + ADK setup, live verify, container run
```

**Structure Decision**: Keep the existing single `src`-layout library + thin `entrypoint/`
consumer (Constitution Principle I). The re-platform is contained to `llm.py` (rewrite) and
`prompts.py` (`Settings` only); the loop, training, data-gen, history, and state formats are
untouched so the offline behavioral guarantees carry over unchanged. New files are limited to
the container artifacts and one manual live-verification script.

## Complexity Tracking

> No constitution violations — section intentionally empty.
