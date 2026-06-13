"""US1/US3 experiment tests.

T013 (US1) — fixed-factor isolation: for a shared (dataset, seed) the split, allowlist,
baseline and budget are identical across regimes; ONLY the memory view differs, so the
memory regime is provably the sole manipulated variable (SC-002).

The sweep/resume/failure-isolation tests (T027, US3) are appended in this file once the
orchestrator exists.
"""

from __future__ import annotations

from ds_agent_loop import benchmark as B
from ds_agent_loop import memory, train
from ds_agent_loop.prompts import MemoryRegime, ExperimentRecord

REGIMES = [MemoryRegime.recent_only, MemoryRegime.all_raw, MemoryRegime.compacted_recent]


def _history(n: int) -> list[ExperimentRecord]:
    return [
        ExperimentRecord(
            iteration=i, dataset_size=100, model_name="LinearRegression",
            metrics={"rmse": 10.0 - i}, rationale="r", timestamp="t",
            cell_id="c", seed=0, test_metrics={"rmse": 10.0 - i},
        )
        for i in range(1, n + 1)
    ]


def test_split_is_identical_across_regimes(tmp_path):
    # The split depends only on the dataset, never on the regime (SC-002).
    splits = {r: B.frozen_split("diabetes", state_dir=tmp_path) for r in REGIMES}
    assert splits[MemoryRegime.recent_only] == splits[MemoryRegime.all_raw] == splits[MemoryRegime.compacted_recent]


def test_allowlist_and_baseline_independent_of_regime():
    d = B.get_descriptor("diabetes")
    allowlists = {r: train.allowlist_for(d.task_type) for r in REGIMES}
    assert allowlists[MemoryRegime.recent_only] is allowlists[MemoryRegime.all_raw]
    assert train.BASELINE_BY_TASK[d.task_type] == "LinearRegression"


def test_only_memory_view_differs_across_regimes():
    hist = _history(8)
    views = {
        r: memory.build_view(r, hist, k=3, cell_id="c", iteration=9)
        for r in REGIMES
    }
    # recent_only vs all_raw: the memory slice (and thus the hash) differs...
    assert views[MemoryRegime.recent_only].content_hash != views[MemoryRegime.all_raw].content_hash
    # ...but the underlying history (the fixed factor) is one shared object, unchanged.
    assert [r.iteration for r in hist] == list(range(1, 9))
    # recent_only shows tail-k; all_raw shows everything.
    assert views[MemoryRegime.recent_only].included_record_ids == [6, 7, 8]
    assert views[MemoryRegime.all_raw].included_record_ids == list(range(1, 9))


# --- T015-T019: run_cell end-to-end (offline, deterministic fake proposer) -----------

import asyncio  # noqa: E402

from ds_agent_loop import main  # noqa: E402
from ds_agent_loop import store as S  # noqa: E402
from ds_agent_loop.prompts import CellStatus, NextAction, NextStepDecision, Settings  # noqa: E402


def _settings() -> Settings:
    return Settings(_env_file=None)


def _fixed_propose(model: str = "RandomForestRegressor"):
    """A deterministic proposer that ignores memory — so any cross-regime difference in
    outcomes could ONLY come from memory, which is exactly what SC-002 forbids."""

    async def propose(settings, *, memory_text, allowlist, best_summary, dataset_summary, metric, goal_word):
        return NextStepDecision(action=NextAction.keep_model, model_name=model, hyperparameters={}, reason="keep")

    return propose


def _run(regime, store, *, dataset="diabetes", iterations=4, state_dir, limit=None):
    d = B.get_descriptor(dataset)
    return asyncio.run(
        main.run_cell(
            d, regime, seed=0, k=3, m=10, iterations=iterations, store=store,
            settings=_settings(), state_dir=state_dir, propose=_fixed_propose(),
            context_token_limit=limit,
        )
    )


def test_run_cell_logs_full_trajectory_with_memory_provenance(tmp_path):
    store = S.FakeStore()
    cell = _run(MemoryRegime.recent_only, store, state_dir=tmp_path)
    records = store.get_records(cell.cell_id)
    views = store.get_views(cell.cell_id)
    assert cell.status is CellStatus.completed and len(records) == 4
    assert len(views) == 4
    # every decision recorded its exact memory view (FR-013, Principle XIII)
    hashes = {v.content_hash for v in views}
    assert all(r.memory_view_ref in hashes for r in records)
    assert all("rmse" in r.test_metrics for r in records)


def test_all_raw_prompt_tokens_grow(tmp_path):
    store = S.FakeStore()
    cell = _run(MemoryRegime.all_raw, store, iterations=5, state_dir=tmp_path)
    tokens = [v.prompt_token_count for v in store.get_views(cell.cell_id)]
    assert tokens == sorted(tokens) and tokens[-1] > tokens[0]  # SC-006 unbounded growth


def test_context_limit_stops_all_raw_and_marks_context_limited(tmp_path):
    store = S.FakeStore()
    cell = _run(MemoryRegime.all_raw, store, iterations=20, state_dir=tmp_path, limit=120)
    assert cell.status is CellStatus.context_limited
    assert cell.last_iteration is not None and 1 <= cell.last_iteration < 20
    events = [line["event"] for line in store.get_logs(cell.cell_id)]
    assert "context_limited" in events  # recorded, never silently truncated


def test_memory_is_the_only_difference_across_regimes(tmp_path):
    # SC-002: with a fixed proposer, recent_only and all_raw on the same (dataset, seed)
    # produce byte-identical executed configs and test metrics — only the memory view differs.
    st_recent, st_all = S.FakeStore(), S.FakeStore()
    _run(MemoryRegime.recent_only, st_recent, state_dir=tmp_path)
    _run(MemoryRegime.all_raw, st_all, state_dir=tmp_path)
    rid = main.cell_id_for("diabetes", MemoryRegime.recent_only, 0, 3, 10)
    aid = main.cell_id_for("diabetes", MemoryRegime.all_raw, 0, 3, 10)
    r_recent, r_all = st_recent.get_records(rid), st_all.get_records(aid)
    assert [r.executed_config for r in r_recent] == [r.executed_config for r in r_all]
    assert [r.test_metrics for r in r_recent] == [r.test_metrics for r in r_all]
    # ...but the memory the agent saw differs (all_raw carries more by the last iteration).
    assert st_all.get_views(aid)[-1].prompt_token_count >= st_recent.get_views(rid)[-1].prompt_token_count


def test_completed_cell_is_not_recomputed_on_rerun(tmp_path):
    store = S.FakeStore()
    cell = _run(MemoryRegime.recent_only, store, state_dir=tmp_path)
    before = [r.timestamp for r in store.get_records(cell.cell_id)]
    again = _run(MemoryRegime.recent_only, store, state_dir=tmp_path)  # SC-007
    after = [r.timestamp for r in store.get_records(cell.cell_id)]
    assert again.status is CellStatus.completed and before == after


# --- T027 (US3): the factorial sweep — enumeration, resume, failure isolation --------

from ds_agent_loop import experiment as E  # noqa: E402


def _sweep(store, *, state_dir, datasets, regimes, seeds, propose=None, iterations=3):
    return asyncio.run(
        E.run_sweep(
            _settings(), store=store, state_dir=state_dir, datasets=datasets,
            regimes=regimes, seeds=seeds, iterations=iterations,
            propose=propose or _fixed_propose(),
        )
    )


def test_sweep_enumerates_full_factorial(tmp_path):
    store = S.FakeStore()
    cells = _sweep(
        store, state_dir=tmp_path, datasets=["diabetes", "wine"],
        regimes=["recent_only", "all_raw"], seeds=[0, 1],
    )
    # 2 datasets × 2 regimes × 2 seeds = 8 distinct cells, all completed
    assert len(cells) == 8
    assert len({c.cell_id for c in cells}) == 8
    assert all(c.status is CellStatus.completed for c in cells)


def test_sweep_resume_skips_completed_cells(tmp_path):
    store = S.FakeStore()
    first = _sweep(store, state_dir=tmp_path, datasets=["diabetes"], regimes=["recent_only"], seeds=[0])
    stamps = [r.timestamp for r in store.get_records(first[0].cell_id)]
    second = _sweep(store, state_dir=tmp_path, datasets=["diabetes"], regimes=["recent_only"], seeds=[0])
    assert [r.timestamp for r in store.get_records(first[0].cell_id)] == stamps  # SC-007: no recompute
    assert second[0].status is CellStatus.completed


def test_sweep_isolates_a_failing_cell(tmp_path):
    store = S.FakeStore()

    def _propose_that_breaks_on_wine():
        async def propose(settings, *, memory_text, allowlist, best_summary, dataset_summary, metric, goal_word):
            if "wine" in dataset_summary:
                raise RuntimeError("synthetic training error")
            return NextStepDecision(action=NextAction.keep_model, model_name="RandomForestRegressor", hyperparameters={}, reason="keep")
        return propose

    cells = _sweep(
        store, state_dir=tmp_path, datasets=["diabetes", "wine"],
        regimes=["recent_only"], seeds=[0], propose=_propose_that_breaks_on_wine(),
    )
    by_dataset = {c.dataset_id: c for c in cells}
    assert by_dataset["wine"].status is CellStatus.failed
    assert by_dataset["wine"].error and "synthetic training error" in by_dataset["wine"].error
    assert by_dataset["diabetes"].status is CellStatus.completed  # sibling unaffected (FR-015)


def test_sweep_exit_code_zero_only_when_all_terminal():
    from ds_agent_loop.prompts import ExperimentCell, MemoryRegime as MR

    def cell(status):
        return ExperimentCell(cell_id="x", dataset_id="d", regime=MR.recent_only, seed=0, k=5, m=10, budget=10, status=status)

    assert E.sweep_exit_code([cell(CellStatus.completed), cell(CellStatus.failed), cell(CellStatus.context_limited)]) == 0
    assert E.sweep_exit_code([cell(CellStatus.completed), cell(CellStatus.running)]) == 1


# --- T041 (US5): k/m grid produces distinct, comparable cells (FR-025) ----------------


def test_sweep_grid_over_k_creates_distinct_cells(tmp_path):
    store = S.FakeStore()
    cells = asyncio.run(
        E.run_sweep(
            _settings(), store=store, state_dir=tmp_path, datasets=["diabetes"],
            regimes=["recent_only"], seeds=[0], grid_k=[3, 5], grid_m=[10], iterations=3,
            propose=_fixed_propose(),
        )
    )
    assert len(cells) == 2
    ids = {c.cell_id for c in cells}
    assert any("k3" in i for i in ids) and any("k5" in i for i in ids)  # distinct, comparable cells
    assert all(c.status is CellStatus.completed for c in cells)
