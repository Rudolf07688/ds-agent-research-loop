# Quickstart: Memory-Compaction Ablation (Directional Research Memory)

**Feature**: `003-memory-compaction-ablation` | **Gate**: constitution v5.1.0

All commands run via `uv` (Principle VI). A full sweep runs in the container with Postgres
(Principle X). Authentication is ADC (no API key) — `gcloud auth application-default login` once.

## 0. Prerequisites

```bash
uv sync                         # resolves new deps: sqlalchemy, psycopg[binary], alembic, scipy, matplotlib
gcloud auth application-default login   # ADC for Vertex/Gemini
cp .env.example .env            # set DATABASE_URL, benchmark/regime/k/m/seeds (sane defaults baked in)
```

The Postgres schema is owned by **Alembic** migrations (`alembic/`, constitution Principle IV). The
single-cell runner, the sweep, and the container entrypoint all run `alembic upgrade head`
automatically at startup, so a fresh database is migrated before any cell runs — no manual step.
To apply migrations by hand: `uv run alembic upgrade head` (and `uv run alembic revision
--autogenerate -m "..."` when you change the schema in `store.py`).

## 1. Run a single cell (US1 — the irreducible slice)

One `(dataset × regime × seed)` trajectory, fully logged:

```bash
uv run python -m ds_agent_loop.main \
  --dataset delivery_time --regime recent_only --seed 0 --k 5 --iterations 30
```

Confirm: a per-iteration log where each row records the exact memory shown (`memory_view_ref`), the
proposal, the executed config, and val/test metrics. Re-run with `--regime all_raw --seed 0` and
verify the ONLY difference is the memory slice (SC-002).

## 2. Run Condition C with compaction (US2 — Directional Research Memory)

```bash
uv run python -m ds_agent_loop.main \
  --dataset delivery_time --regime compacted_recent --seed 0 --k 5 --m 10 --iterations 30
```

Confirm: a `DirectionalMemory` artifact is generated at each multiple of `m`, validated against the
belief schema, persisted with `source_record_ids` lineage (built only from records at/before the
trigger — SC-005), and that the agent thereafter sees `artifact + last k` (never full history).

## 3. Run the full factorial sweep (US3) in the container

```bash
docker compose up --build       # brings up Postgres, runs every (dataset×regime×seed) cell to budget, exits 0
```

Confirm (Principle X): clean start, waits for healthy Postgres, every cell completes or is recorded
`failed` without aborting siblings (FR-015), correct exit status. Interrupt and re-run — completed
cells are NOT recomputed (SC-007).

## 4. Export inspectable state (Principle IV / FR-014a)

```bash
uv run python -m ds_agent_loop.store export --out outputs/export
# -> per-cell records.json / memory_views.json / artifacts.json / logs.csv + cells.csv + outcomes.json
```

## 5. Analyze (US4 — outcomes, paired tests, plots)

```bash
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis
```

Produces: primary outcome (best test score under budget) + secondary outcomes per condition;
per-dataset paired comparisons A-vs-B / B-vs-C / A-vs-C (Wilcoxon + bootstrap CIs, FR-021);
improvement & token-growth curves; and an HTML progress note under `notes/` (Principle VII).

## 6. (Optional) Threshold sweep over k and m (US5 — phase transition, Principle XIV)

```bash
uv run python -m ds_agent_loop.experiment sweep --grid-k 3,5,10 --grid-m 5,10,20
uv run python -m ds_agent_loop.analysis --threshold-curves --from outputs/export
```

Produces performance-vs-`k` and performance-vs-`m` curves to locate where raw history begins to hurt.

## Tests (offline, hermetic — zero network)

```bash
uv run pytest        # stubbed ADK/genai agent + store seam; deterministic machinery covered (Principle XI)
```

## Map to success criteria

| Step | Validates |
|------|-----------|
| 1 | SC-001, SC-002 (isolated manipulation) |
| 2 | SC-005 (no future leakage), Principle XII |
| 3 | SC-003, SC-007 (sweep completeness + resume) |
| 4 | FR-014a (inspectable export) |
| 5 | SC-004, SC-006, SC-008 (comparisons, token growth, hypotheses) |
| 6 | FR-025 (threshold curves) |
