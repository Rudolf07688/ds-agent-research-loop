"""Container batch entrypoint: run the memory-regime ablation SWEEP to completion.

Brings up against Postgres (via ``DATABASE_URL``), runs every configured
(dataset × regime × seed [× k × m]) cell to budget, exports the inspectable JSON/CSV, and
exits with a status that is 0 only if every cell is terminal (Principle X).

Set ``STUB_LLM=1`` to run with a deterministic in-process agent (NO network) — used to
validate the full container plumbing (Postgres + sweep + logs + export + exit code) without
Vertex credentials. Leave it unset for a real research sweep against Vertex/Gemini.

    uv run python entrypoint/run.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ds_agent_loop import store as store_mod
from ds_agent_loop.experiment import run_sweep, sweep_exit_code
from ds_agent_loop.prompts import DirectionalMemory, NextAction, NextStepDecision

from config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def _stub_enabled() -> bool:
    return os.getenv("STUB_LLM", "").lower() in ("1", "true", "yes")


async def _stub_propose(settings, *, memory_text, allowlist, best_summary, dataset_summary, metric, goal_word):
    """Deterministic, offline next-step proposer: switch to the second allowlisted model."""

    model = allowlist[1] if len(allowlist) > 1 else allowlist[0]
    return NextStepDecision(action=NextAction.switch_model, model_name=model, hyperparameters={}, reason="stub")


async def _stub_compactor(settings, *, source_records, descriptor):
    """Deterministic, offline Directional Research Memory artifact."""

    return DirectionalMemory(
        confirmed_findings=[f"{len(source_records)} experiments compacted"],
        failed_directions=[],
        promising_directions=["keep exploring allowlisted models"],
        best_known_configs=[],
        unresolved_questions=[],
        next_step_recommendation="continue",
        confidence=0.5,
        rationale="stub compaction",
    ).model_dump(mode="json")


def main() -> None:
    config = load_config()
    engine = store_mod.make_engine(config.database_url)
    store = store_mod.Store(engine)

    stub = _stub_enabled()
    propose = _stub_propose if stub else None
    compactor = _stub_compactor if stub else None
    mode = "STUB (offline)" if stub else "Vertex/Gemini"
    print(f"Running ablation sweep [{mode}] -> Postgres at {config.database_url.split('@')[-1]}")

    cells = asyncio.run(run_sweep(config, store=store, propose=propose, compactor=compactor))

    out_dir = REPO_ROOT / "outputs" / "export"
    store_mod.export(store, out_dir)
    completed = sum(c.status.value == "completed" for c in cells)
    failed = sum(c.status.value == "failed" for c in cells)
    limited = sum(c.status.value == "context_limited" for c in cells)
    code = sweep_exit_code(cells)
    print(
        f"Sweep done: {len(cells)} cells "
        f"({completed} completed, {limited} context_limited, {failed} failed). "
        f"Export -> {out_dir}. Exit {code}."
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
