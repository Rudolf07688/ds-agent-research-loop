"""US4 analysis tests (T033) — outcomes, regret, paired tests, plots, note.

Builds a deterministic fixture export (via FakeStore + store.export) and runs the analysis,
checking metric-direction-awareness, the regret-style measure (Principle XIV), the three
paired comparisons with bootstrap CIs (FR-021), and that plots + the notes/ note are written.
"""

from __future__ import annotations

import json

from ds_agent_loop import analysis as A
from ds_agent_loop import store as S
from ds_agent_loop.prompts import (
    CellStatus,
    ExperimentCell,
    ExperimentRecord,
    MemoryRegime,
    MemoryView,
)


def _add_cell(store, dataset_id, regime, seed, metric_name, series, token_step=10):
    regime = MemoryRegime(regime)
    cid = f"{dataset_id}|{regime.value}|s{seed}|k5|m10"
    store.upsert_cell(
        ExperimentCell(cell_id=cid, dataset_id=dataset_id, regime=regime, seed=seed, k=5, m=10,
                       budget=len(series), status=CellStatus.completed, last_iteration=len(series))
    )
    best = None
    for i, val in enumerate(series, start=1):
        improved = best is None or val < best if metric_name == "rmse" else (best is None or val > best)
        if improved:
            best = val
        store.append_record(
            ExperimentRecord(
                iteration=i, dataset_size=100, model_name="RandomForestRegressor" if i % 2 else "LinearRegression",
                hyperparameters={"n_estimators": i}, metrics={metric_name: val}, rationale="r", timestamp=f"t{i}",
                cell_id=cid, dataset_id=dataset_id, regime=regime, seed=seed, k=5, m=10,
                test_metrics={metric_name: val}, val_metrics={metric_name: val}, improved=improved,
            )
        )
        store.save_view(
            MemoryView(cell_id=cid, iteration=i, regime=regime,
                       included_record_ids=list(range(1, i + 1)), rendered_text="m",
                       content_hash=f"{cid}-{i}", prompt_token_count=20 + i * token_step)
        )
    return cid


def _fixture_store():
    store = S.FakeStore()
    # 3 regression datasets, each with all three regimes; compacted best, all_raw worst.
    for ds in ("diabetes", "delivery_time"):
        _add_cell(store, ds, "recent_only", 0, "rmse", [60, 55, 50])
        _add_cell(store, ds, "all_raw", 0, "rmse", [60, 58, 57])
        _add_cell(store, ds, "compacted_recent", 0, "rmse", [60, 50, 42], token_step=2)
    # a classification dataset (higher-is-better) to exercise direction handling
    _add_cell(store, "wine", "recent_only", 0, "macro_f1", [0.6, 0.7, 0.75])
    _add_cell(store, "wine", "all_raw", 0, "macro_f1", [0.6, 0.62, 0.63])
    _add_cell(store, "wine", "compacted_recent", 0, "macro_f1", [0.6, 0.8, 0.9], token_step=2)
    return store


def test_cell_outcome_regression_uses_min_rmse_and_reports_regret():
    store = S.FakeStore()
    cid = _add_cell(store, "diabetes", "recent_only", 0, "rmse", [60, 55, 50])
    cell = store.get_cell(cid).model_dump(mode="json")
    o = A.cell_outcome(cell, [r.model_dump(mode="json") for r in store.get_records(cid)],
                       [v.model_dump(mode="json") for v in store.get_views(cid)])
    assert o.primary_metric == "rmse"
    assert o.primary_outcome == 50.0  # best (lowest) test RMSE under budget
    assert o.primary_signed == -50.0  # direction-normalized
    assert "best_so_far_regret" in o.secondary and o.secondary["best_so_far_regret"] >= 0  # XIV


def test_cell_outcome_classification_uses_max_f1():
    store = S.FakeStore()
    cid = _add_cell(store, "wine", "compacted_recent", 0, "macro_f1", [0.6, 0.8, 0.9])
    cell = store.get_cell(cid).model_dump(mode="json")
    o = A.cell_outcome(cell, [r.model_dump(mode="json") for r in store.get_records(cid)],
                       [v.model_dump(mode="json") for v in store.get_views(cid)])
    assert o.primary_outcome == 0.9 and o.primary_signed == 0.9


def test_paired_comparisons_cover_three_hypotheses():
    store = _fixture_store()
    outcomes = []
    for c in store.all_cells():
        cell = c.model_dump(mode="json")
        outcomes.append(
            A.cell_outcome(cell, [r.model_dump(mode="json") for r in store.get_records(c.cell_id)],
                           [v.model_dump(mode="json") for v in store.get_views(c.cell_id)])
        )
    comparisons = A.paired_comparisons(outcomes)
    names = {c.comparison for c in comparisons}
    assert names == {"A_vs_B", "B_vs_C", "A_vs_C"}
    for c in comparisons:
        assert c.n_datasets == 3 and c.effect is not None
    # compaction (C) should beat all_raw (B): B_vs_C effect < 0 (x=B worse than y=C)
    bc = next(c for c in comparisons if c.comparison == "B_vs_C")
    assert bc.effect < 0


def test_analyze_end_to_end_writes_outputs(tmp_path):
    store = _fixture_store()
    export_dir = tmp_path / "export"
    S.export(store, export_dir)
    out_dir = tmp_path / "analysis"
    notes_dir = tmp_path / "notes"
    summary = A.analyze(export_dir, out_dir, with_threshold_curves=True, notes_dir=notes_dir)

    assert (out_dir / "outcomes.json").exists()
    assert (out_dir / "token_growth.png").exists()
    assert (out_dir / "paired_differences.png").exists()
    assert (notes_dir / "ablation_results.html").exists()
    saved = json.loads((out_dir / "outcomes.json").read_text())
    assert len(saved["outcomes"]) == 9 and len(saved["comparisons"]) == 3
    assert "threshold_curves" in saved
    assert all("best_so_far_regret" in o["secondary"] for o in saved["outcomes"])


def test_threshold_curves_over_k_and_m():
    # T041 (US5): threshold curves derivable from a recorded (k, m) grid (FR-025).
    outs = [
        A.OutcomeSummary(
            cell_id=f"c{i}", dataset_id="diabetes", regime="recent_only", seed=0,
            k=k, m=m, primary_metric="rmse", primary_outcome=v, primary_signed=-v, secondary={},
        )
        for i, (k, m, v) in enumerate([(3, 10, 50.0), (5, 10, 45.0), (5, 20, 47.0)])
    ]
    curves = A.threshold_curves(outs)
    assert set(curves["performance_vs_k"]["recent_only"].keys()) == {"3", "5"}
    assert set(curves["performance_vs_m"]["recent_only"].keys()) == {"10", "20"}
