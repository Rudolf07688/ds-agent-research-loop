# Contract: Sweep / cell / analyze CLI + settings

All entry points run via `uv run` (Principle VI) and read the single `Settings` object (Principle
VIII); CLI flags override settings at call time. The container batch job (`entrypoint/run.py`)
invokes the sweep.

## Settings (added fields on the existing `Settings`)

| field (env var) | default | meaning |
|-----------------|---------|---------|
| `database_url` (`DATABASE_URL`) | compose value | Postgres connection (Principle IV) |
| `benchmark_version` | `v1` | stamped on every cell (Principle IX) |
| `datasets` | full suite | dataset ids to include |
| `regimes` | `recent_only,all_raw,compacted_recent` | regimes to run (Principle XIII) |
| `seeds` | `0,1,2,3,4` | cell seeds |
| `recent_k` (`RECENT_K`) | `5` | recent-window `k` |
| `compaction_m` (`COMPACTION_M`) | `10` | compaction cadence `m` |
| `n_iterations` | `30` | per-cell budget `N` |
| `compaction_token_threshold` (`t`) | unset | optional FR-024 trigger |

Existing Vertex/Gemini fields (`google_cloud_project`, `google_cloud_location`, `gemini_model`,
`use_vertexai`) are unchanged.

## Single cell (US1/US2)

```
python -m ds_agent_loop.main \
  --dataset <id> --regime <recent_only|all_raw|compacted_recent> \
  --seed <int> --k <int> [--m <int>] --iterations <int>
```

Runs one `(dataset × regime × seed [× k × m])` cell to budget; persists records, memory views, and
(regime C) compaction artifacts; resumes if the cell already has progress.

## Full sweep (US3/US5)

```
python -m ds_agent_loop.experiment sweep \
  [--datasets a,b,c] [--regimes ...] [--seeds 0,1,2] \
  [--grid-k 3,5,10] [--grid-m 5,10,20]
```

- Enumerates the factorial of datasets × regimes × seeds (× k × m grid for US5).
- Skips any cell with `status=completed` (resume; SC-007); a failed cell is recorded and does NOT
  abort siblings (FR-015).
- Exit code 0 only if every cell is `completed` or `failed` (no cell left `running`); the container
  job surfaces this status (Principle X).

## Export & analyze (US4)

```
python -m ds_agent_loop.store export --out outputs/export
python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis [--threshold-curves]
```

`analysis` emits primary/secondary outcomes, paired comparisons (A-vs-B, B-vs-C, A-vs-C) with
bootstrap CIs, improvement & token-growth curves, optional threshold curves, and a progress note
under `notes/` (Principles XIV, VII). Every number is regenerable from the export (Principle XI).
