"""The cell orchestrator: the factorial sweep over (dataset × regime × seed × k × m).

Runs every cell to budget, isolated and resumable (FR-011/012/015, SC-007): a completed
cell is skipped (no recompute), and a cell that errors is recorded ``failed`` with its error
WITHOUT aborting its siblings. Each cell is stamped with reproduction provenance — commit,
settings snapshot, benchmark version, split — so every result is replayable (Principle IX).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from itertools import product
from pathlib import Path

from . import benchmark, compaction
from . import store as store_mod
from .main import STATE_DIR, cell_id_for, run_cell
from .prompts import CellStatus, ExperimentCell, MemoryRegime, Settings


def _git_commit() -> str:
    """Best-effort current commit for the repro stamp (Principle IX); 'unknown' if absent."""

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _settings_snapshot(settings: Settings) -> dict:
    return {
        "gemini_model": settings.gemini_model,
        "n_iterations": settings.n_iterations,
        "benchmark_version": settings.benchmark_version,
    }


def _resolve(values: list | None, fallback: list) -> list:
    return values if values else fallback


async def run_sweep(
    settings: Settings,
    *,
    store,
    state_dir: Path = STATE_DIR,
    datasets: list[str] | None = None,
    regimes: list[str] | None = None,
    seeds: list[int] | None = None,
    grid_k: list[int] | None = None,
    grid_m: list[int] | None = None,
    iterations: int | None = None,
    propose=None,
    compactor=None,
    context_token_limit: int | None = None,
) -> list[ExperimentCell]:
    """Enumerate and run the full factorial. Returns every cell's final state."""

    dataset_ids = _resolve(datasets, settings.datasets) or benchmark.DEFAULT_SUITE_IDS
    regime_vals = _resolve(regimes, settings.regimes)
    seed_vals = _resolve(seeds, settings.seeds)
    k_vals = _resolve(grid_k, [settings.recent_k])
    m_vals = _resolve(grid_m, [settings.compaction_m])
    n_iter = iterations or settings.n_iterations
    repro = {"commit": _git_commit(), "settings": _settings_snapshot(settings)}

    # Resolve every member from the materialized, versioned suite (US4): materialize once
    # (idempotent), then load each member's descriptor + frozen split by id.
    benchmark.materialize_suite(store, list(dataset_ids), version=settings.benchmark_version)
    resolved = {
        d: benchmark.load_member(store, d, version=settings.benchmark_version)
        for d in dataset_ids
    }

    results: list[ExperimentCell] = []
    for dataset_id, regime_v, seed, k, m in product(dataset_ids, regime_vals, seed_vals, k_vals, m_vals):
        regime = MemoryRegime(regime_v)
        descriptor, split, _ = resolved[dataset_id]
        cid = cell_id_for(dataset_id, regime, seed, k, m)
        cell_compactor = (compactor or compaction.compact) if regime is MemoryRegime.compacted_recent else None
        try:
            cell = await run_cell(
                descriptor, regime, seed, k=k, m=m, iterations=n_iter,
                store=store, settings=settings, state_dir=state_dir,
                propose=propose, split=split, compactor=cell_compactor,
                context_token_limit=context_token_limit,
                compaction_token_threshold=settings.compaction_token_threshold,
                repro=repro,
            )
        except Exception as exc:  # one cell's failure MUST NOT abort the sweep (FR-015)
            log = store_mod.get_logger(store, cid)
            log.error("cell_failed", error=str(exc), error_type=type(exc).__name__)
            failed = store.get_cell(cid) or ExperimentCell(
                cell_id=cid, dataset_id=dataset_id, regime=regime, seed=seed, k=k, m=m,
                budget=n_iter, status=CellStatus.failed,
            )
            failed = failed.model_copy(update={"status": CellStatus.failed, "error": str(exc)})
            store.upsert_cell(failed)
            cell = failed
        results.append(cell)
    return results


def sweep_exit_code(cells: list[ExperimentCell]) -> int:
    """0 only if every cell is terminal (none left ``running``/``pending``) — Principle X."""

    terminal = {CellStatus.completed, CellStatus.context_limited, CellStatus.failed}
    return 0 if all(c.status in terminal for c in cells) else 1


# ---------------------------------------------------------------------------
# CLI (contracts/runner-cli.md §Full sweep)
# ---------------------------------------------------------------------------


def _csv_ints(value: str) -> list[int]:
    return [int(x) for x in value.split(",") if x.strip()]


def _csv_strs(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _parse_args(settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the memory-regime ablation sweep.")
    sub = parser.add_subparsers(dest="command", required=True)
    sweep = sub.add_parser("sweep", help="run every (dataset × regime × seed [× k × m]) cell")
    sweep.add_argument("--datasets", type=_csv_strs, default=None)
    sweep.add_argument("--regimes", type=_csv_strs, default=None)
    sweep.add_argument("--seeds", type=_csv_ints, default=None)
    sweep.add_argument("--grid-k", type=_csv_ints, default=None, dest="grid_k")
    sweep.add_argument("--grid-m", type=_csv_ints, default=None, dest="grid_m")
    sweep.add_argument("--iterations", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    settings = Settings()
    args = _parse_args(settings)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    store_mod.upgrade_to_head(settings.database_url)  # schema owned by Alembic (Principle IV)
    engine = store_mod.make_engine(settings.database_url)
    store = store_mod.Store(engine)
    cells = asyncio.run(
        run_sweep(
            settings, store=store, datasets=args.datasets, regimes=args.regimes,
            seeds=args.seeds, grid_k=args.grid_k, grid_m=args.grid_m, iterations=args.iterations,
        )
    )
    completed = sum(c.status is CellStatus.completed for c in cells)
    failed = sum(c.status is CellStatus.failed for c in cells)
    limited = sum(c.status is CellStatus.context_limited for c in cells)
    print(
        f"Sweep finished: {len(cells)} cells "
        f"({completed} completed, {limited} context_limited, {failed} failed). "
        f"Export with `python -m ds_agent_loop.store export`."
    )
    sys.exit(sweep_exit_code(cells))


if __name__ == "__main__":
    main()
