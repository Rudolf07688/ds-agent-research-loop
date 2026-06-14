# Operating This Repo — Run / Interpret / Find Faults

A practical operator's guide. Verified by actually running the loop, compaction, and all
three provenance audits in-process (incl. deliberate tampering). Pairs with `notes/DEMO.md`
(narrated walkthrough) and `notes/flow.md` (code-level trace).

## Mental model (analogies)

- **A cell** = one experiment run, addressed `member|regime|s<seed>|k<k>|m<m>`
  (e.g. `wine|compacted_recent|s0|k5|m3`). Think of it like a single CI build keyed by its config.
- **The study** = run the *same* cell under different **memory regimes** and compare. Like
  A/B testing a chatbot's context-window strategy — same task, same budget, only memory differs.
- **Postgres** = the lab notebook. Every decision, the exact memory shown, and every compaction
  artifact is persisted so the whole run is **replayable** and **auditable** (like git history for
  experiments).
- **STUB_LLM=1** = offline mode. Swaps the real Gemini/Vertex calls for deterministic in-process
  stubs, so everything runs with no credentials and no network.

## The three CLIs (entry points)

- `ds-agent-loop`  → `main.main` — run ONE cell (the experiment loop).
- `ds-agent-memory` → `provenance.main` — replay / audit / compaction (fault-finding; **zero LLM calls**).
- `ds-agent-data`  → `data_gen.main` — grow the *expandable* synthetic dataset (separate from the
  frozen benchmark suite).

Equivalent module forms: `python -m ds_agent_loop.main`, `... .store export`, `... .analysis`.

## 0. Prerequisites

- Python **3.13** + `uv` (the canonical path: `uv sync`, then `uv run <cmd>`).
- **Postgres** reachable at `DATABASE_URL`
  (default `postgresql+psycopg://autods:autods@localhost:5432/autods`).
  Bring it up with `docker compose up -d db` (Postgres 17 on :5432).
- For **real** (non-stub) runs only: Vertex ADC via `gcloud auth application-default login` + a `.env`.

## 1. Run

```bash
# Whole story, offline, ~30s — the fastest way to see it work:
./scripts/demo.sh

# One cell by hand (offline):
STUB_LLM=1 uv run ds-agent-loop --member wine --seed 0 \
    --regime compacted_recent --k 5 --m 3 --iterations 9
```

Datasets (benchmark members): `delivery_time`, `diabetes`, `breast_cancer` (clf), `wine` (clf), `iris` (clf).
Regimes: `recent_only` | `all_raw` | `compacted_recent`.

Key knobs (CLI flag / env): `--member`, `--regime`/`REGIME`, `--seed`, `--k`/`RECENT_K` (memory tail),
`--m`/`COMPACTION_M` (compaction cadence), `--iterations`/`N_ITERATIONS`, `--context-token-limit`,
`DATABASE_URL`, `BENCHMARK_VERSION`, `STUB_LLM`.

The full offline sweep: `STUB_LLM=1 uv run python entrypoint/run.py`
(scope it with `SEEDS=0,1 DATASETS=wine REGIMES=recent_only,compacted_recent`).

## 2. Interpret results

**Live, per iteration** — structured JSON logs (stdout + Postgres). Watch `iteration_done`:
- `prompt_token_count` — how big the memory view was (the H1 evidence: does growing history hurt?).
- `included_records` — how many raw records were in the prompt.
- `improved` / `rejected` — whether the chosen model beat best-so-far; whether the proposal was
  rejected (out-of-allowlist or out-of-action-space → previous model retained).
- `memory_view_ref` — content hash of the exact memory shown (the anchor for replay).

`compaction_done` fires every `m` iters (regime C): `source_records`, `cadence`, `mode`.

**Token-growth signature (verified on `wine`, 9 iters, k=5, m=3):**
- `recent_only` plateaus once the tail fills: `17,65,119,172,226,279,279,279,279`.
- `compacted_recent` jumps when an artifact enters the prompt, then holds: `…119,250,303,357,…`.
- `all_raw` is the regime expected to grow unbounded (stopped + marked `context_limited` if it
  exceeds `--context-token-limit`, never silently truncated).

**After the run — export + analyse:**
```bash
uv run python -m ds_agent_loop.store export --out outputs/export
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis
```
- `outputs/export/` — `cells`, per-iteration `records`, and `artifacts.json` (full source→artifact lineage).
- `outputs/analysis/` — `outcomes.json`, `token_growth.png`, `paired_differences.png`.
- `notes/ablation_results.html` — self-contained report; open in a browser when demoing.

Primary outcome = best test score under budget; secondary = trajectory/regret curves + paired
A-vs-B / B-vs-C / A-vs-C comparisons.

## 3. Find faults

The `ds-agent-memory` audits read **only persisted state** and make **zero LLM calls** — they are
deterministic and fail loudly with the offending iteration/record named.

```bash
# Verified replay: rebuild every decision's memory view from history; assert hash-exact match.
uv run ds-agent-memory replay --cell 'wine|recent_only|s0|k5|m3'   # or --all

# Cross-regime audit: prove two cells differ ONLY in memory (equal config fingerprint).
uv run ds-agent-memory audit \
    --cell-a 'wine|recent_only|s0|k5|m3' --cell-b 'wine|compacted_recent|s0|k5|m3'

# Compaction lineage: reconstruct the records at/before each trigger; assert == recorded sources.
uv run ds-agent-memory compaction 'wine|compacted_recent|s0|k5|m3'
```

**What each catch looks like (verified by deliberate tampering):**
- Corrupt a record's `memory_view_ref` → `replay` reports `ok=False`, `matched=8/9`, names the bad
  iteration. → a decision's memory wasn't what we claim it was.
- Inject a phantom source id into an artifact → `compaction` reports `ok=False`,
  `history_disagreement` on that record. → lineage doesn't match raw history.
- `audit` mismatch → `fingerprint_equal=False` + the first contaminating held-fixed factor named.
  → the comparison is NOT memory-only; something else changed.

**Replay caveat:** hash-exact only for cells recorded by the current builder. Cells recorded
before the `memory.py` `sort_keys` rendering fix report spurious per-iteration mismatches —
regenerate them.

### Common operational faults & first checks
- **`could not connect` / startup hang** → Postgres isn't up. `docker compose up -d db`; check `DATABASE_URL`.
- **Schema/relation errors** → migrations not applied. The loop calls `alembic upgrade head` itself;
  run it manually if using a module path directly: `uv run alembic upgrade head`.
- **Unknown regime** → fails fast at startup by design (no silent default). Check `--regime`/`REGIME`.
- **`BenchmarkDriftError`** → a fixed factor changed without a `BENCHMARK_VERSION` bump. Bump the version.
- **`cell … refusing to resume under regime/k`** → you re-ran an existing cell id with a different
  memory variable. Cells are immutable in their controlled variable; use a new id.
- **Real-LLM run fails fast** → missing ADC. `gcloud auth application-default login`, or use `STUB_LLM=1`.

## 4. Test & verify the code itself

```bash
uv run pytest                         # hermetic offline suite; no network/LLM
uv run python entrypoint/smoke_live.py   # ONE real Vertex round-trip (excluded from pytest)
```
Suite status: **136 passed, 7 skipped** (the 7 skips are the Postgres integration tests, which need
a live DB). Coverage spans data-gen, validation/allowlist, the loop, memory views, compaction
lineage, provenance replay/audit, and analysis.

## Key files (where to look when something breaks)

| Concern | File |
|---|---|
| Orchestrator + `run_cell` loop + STUB wiring | `src/ds_agent_loop/main.py` |
| Memory view rendering (`build_view`, `sort_keys`) | `src/ds_agent_loop/memory.py` |
| Compaction operator (`should_compact`, `select_source`, `compact`) | `src/ds_agent_loop/compaction.py` |
| Train / validate / score / allowlist | `src/ds_agent_loop/train.py` |
| Persistence + `export` (Postgres; `FakeStore` for tests) | `src/ds_agent_loop/store.py` |
| Replay + cross-regime + lineage audits | `src/ds_agent_loop/provenance.py` |
| Analysis + HTML report | `src/ds_agent_loop/analysis.py` |
| Schemas, prompts, `Settings` | `src/ds_agent_loop/prompts.py` |
| Vertex/Gemini wrapper (real LLM) | `src/ds_agent_loop/llm.py` |
```
