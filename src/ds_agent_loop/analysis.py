"""Outcomes, paired significance tests, curves and the progress note (Principle XIV).

Consumes a completed export (``store.export`` output) and produces, per cell, the primary
outcome (best test score under budget) and the secondary trajectory outcomes — including the
best-so-far **regret curve** required by Principle XIV — then the per-comparison paired tests
(A-vs-B / B-vs-C / A-vs-C) with bootstrap CIs, the improvement/token-growth/paired-difference
plots, optional (k, m) threshold curves, and a human-readable note under ``notes/``. Every
number is regenerable from the export (Principle XI).

All outcomes are metric-direction-aware (FR-023): each value is mapped to a *signed* score
where higher is always better (``direction * metric``), so trajectory and comparison logic is
uniform across regression (RMSE↓) and classification (macro-F1↑) datasets.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless / offline
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402
from scipy import stats  # noqa: E402

from . import benchmark  # noqa: E402

# A=recent_only, B=all_raw, C=compacted_recent. H1: A-vs-B, H2: B-vs-C, H3: A-vs-C.
COMPARISONS = [
    ("A_vs_B", "recent_only", "all_raw", "H1: raw history vs recency"),
    ("B_vs_C", "all_raw", "compacted_recent", "H2: compaction beats all-raw"),
    ("A_vs_C", "recent_only", "compacted_recent", "H3: compaction beats recency"),
]
_BOOT_SEED = 12345
_N_BOOT = 2000


class OutcomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    dataset_id: str
    regime: str
    seed: int
    k: int
    m: int
    primary_metric: str
    primary_outcome: float  # raw best test score under budget (FR-019)
    primary_signed: float  # direction-normalized (higher = better)
    secondary: dict[str, Any] = Field(default_factory=dict)


class PairedComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison: str
    hypothesis: str
    regime_x: str
    regime_y: str
    n_datasets: int
    effect: float | None  # mean relative effect (x vs y), >0 means x better
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    test: str


# ---------------------------------------------------------------------------
# Load export
# ---------------------------------------------------------------------------


def load_export(export_dir: str | Path) -> dict[str, Any]:
    """Read cells.csv + per-cell records.json / memory_views.json from an export dir."""

    export_dir = Path(export_dir)
    cells_csv = export_dir / "cells.csv"
    if not cells_csv.exists():
        raise FileNotFoundError(f"No cells.csv under {export_dir}; run `store export` first.")
    cells: list[dict] = []
    with cells_csv.open() as fh:
        for row in csv.DictReader(fh):
            row["seed"], row["k"], row["m"] = int(row["seed"]), int(row["k"]), int(row["m"])
            cells.append(row)
    records, views = {}, {}
    for c in cells:
        cell_dir = export_dir / _safe_dir(c["cell_id"])
        records[c["cell_id"]] = _read_json(cell_dir / "records.json")
        views[c["cell_id"]] = _read_json(cell_dir / "memory_views.json")
    return {"cells": cells, "records": records, "views": views}


def _read_json(path: Path) -> list:
    return json.loads(path.read_text()) if path.exists() else []


def _safe_dir(cell_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cell_id)


# ---------------------------------------------------------------------------
# Per-cell outcomes (FR-019/020, Principle XIV)
# ---------------------------------------------------------------------------


def _signed(value: float, direction: int) -> float:
    return direction * value


# numpy 2.0 renamed trapz -> trapezoid; support both.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def cell_outcome(cell: dict, records: list[dict], views: list[dict]) -> OutcomeSummary | None:
    """Compute the primary + secondary outcomes for one cell (metric-direction-aware)."""

    descriptor = benchmark.get_descriptor(cell["dataset_id"])
    metric, direction = descriptor.primary_metric, descriptor.metric_direction
    records = [r for r in records if r.get("test_metrics", {}).get(metric) is not None]
    if not records:
        return None

    signed = [_signed(r["test_metrics"][metric], direction) for r in records]
    raw = [r["test_metrics"][metric] for r in records]
    best_signed = np.maximum.accumulate(signed)  # running best (higher = better)
    final_best = float(best_signed[-1])
    primary_signed = final_best
    # raw best under budget (FR-019): undo the sign
    primary_outcome = final_best * direction

    # best-so-far regret curve (Principle XIV): Σ_t (final_best − best_so_far_t) >= 0
    regret = float(np.sum(final_best - best_signed))
    # improving steps + AUC of the best-so-far signed trajectory
    improving_steps = sum(1 for r in records if r.get("improved"))
    auc_improvement = float(_trapezoid(best_signed))
    # iterations to reach 90% of the total signed improvement over the first record
    start = best_signed[0]
    span = final_best - start
    if span > 0:
        target = start + 0.9 * span
        iters_to_90 = int(np.argmax(best_signed >= target)) + 1
    else:
        iters_to_90 = 1
    # repetition rate: fraction of iterations whose (model, hp) signature already appeared
    seen, repeats = set(), 0
    for r in records:
        sig = (r.get("model_name"), json.dumps(r.get("hyperparameters", {}), sort_keys=True))
        if sig in seen:
            repeats += 1
        seen.add(sig)
    repetition_rate = repeats / len(records)
    distinct_models = len({r.get("model_name") for r in records})
    distinct_configs = len(seen)
    # token growth from the persisted memory views
    token_by_iter = {v["iteration"]: v["prompt_token_count"] for v in views}
    tokens = [token_by_iter[i] for i in sorted(token_by_iter)]

    return OutcomeSummary(
        cell_id=cell["cell_id"], dataset_id=cell["dataset_id"], regime=cell["regime"],
        seed=cell["seed"], k=cell["k"], m=cell["m"], primary_metric=metric,
        primary_outcome=primary_outcome, primary_signed=primary_signed,
        secondary={
            "best_so_far_regret": regret,
            "auc_improvement": auc_improvement,
            "improving_steps": improving_steps,
            "iters_to_90pct": iters_to_90,
            "repetition_rate": repetition_rate,
            "distinct_models": distinct_models,
            "distinct_configs": distinct_configs,
            "final_token_count": tokens[-1] if tokens else 0,
            "token_growth": (tokens[-1] - tokens[0]) if len(tokens) > 1 else 0,
            "best_signed_trajectory": [float(x) for x in best_signed],
            "token_trajectory": tokens,
        },
    )


# ---------------------------------------------------------------------------
# Paired comparisons (FR-021)
# ---------------------------------------------------------------------------


def _bootstrap_ci(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(_BOOT_SEED)
    means = [float(rng.choice(arr, size=len(arr), replace=True).mean()) for _ in range(_N_BOOT)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _regime_means_by_dataset(outcomes: list[OutcomeSummary]) -> dict[str, dict[str, float]]:
    """dataset -> regime -> mean signed primary outcome across seeds (and any k/m)."""

    acc: dict[str, dict[str, list[float]]] = {}
    for o in outcomes:
        acc.setdefault(o.dataset_id, {}).setdefault(o.regime, []).append(o.primary_signed)
    return {ds: {rg: float(np.mean(v)) for rg, v in regs.items()} for ds, regs in acc.items()}


def paired_comparisons(outcomes: list[OutcomeSummary]) -> list[PairedComparison]:
    by_ds = _regime_means_by_dataset(outcomes)
    results: list[PairedComparison] = []
    for name, rx, ry, hyp in COMPARISONS:
        rel_diffs: list[float] = []
        for ds, regs in by_ds.items():
            if rx in regs and ry in regs:
                x, y = regs[rx], regs[ry]
                denom = abs(y) if abs(y) > 1e-12 else 1.0
                rel_diffs.append((x - y) / denom)  # >0 => regime x better (signed)
        n = len(rel_diffs)
        effect = float(np.mean(rel_diffs)) if n else None
        ci_low, ci_high = _bootstrap_ci(rel_diffs) if n >= 2 else (None, None)
        p_value, test = _paired_p(rel_diffs)
        results.append(
            PairedComparison(
                comparison=name, hypothesis=hyp, regime_x=rx, regime_y=ry, n_datasets=n,
                effect=effect, ci_low=ci_low, ci_high=ci_high, p_value=p_value, test=test,
            )
        )
    return results


def _paired_p(diffs: list[float]) -> tuple[float | None, str]:
    arr = np.asarray(diffs, dtype=float)
    if len(arr) < 2 or np.allclose(arr, 0):
        return (None, "none")
    try:
        return (float(stats.wilcoxon(arr).pvalue), "wilcoxon")
    except Exception:
        try:
            return (float(stats.ttest_1samp(arr, 0.0).pvalue), "paired_t")
        except Exception:
            return (None, "none")


# ---------------------------------------------------------------------------
# Threshold curves (FR-025, US5)
# ---------------------------------------------------------------------------


def threshold_curves(outcomes: list[OutcomeSummary]) -> dict[str, Any]:
    """Performance vs k and vs m, per regime (signed primary, averaged)."""

    def _curve(param: str) -> dict[str, dict[str, float]]:
        acc: dict[str, dict[Any, list[float]]] = {}
        for o in outcomes:
            val = getattr(o, param)
            acc.setdefault(o.regime, {}).setdefault(val, []).append(o.primary_signed)
        return {rg: {str(p): float(np.mean(v)) for p, v in pts.items()} for rg, pts in acc.items()}

    return {"performance_vs_k": _curve("k"), "performance_vs_m": _curve("m")}


# ---------------------------------------------------------------------------
# Plots (FR-022) + progress note (Principle VII)
# ---------------------------------------------------------------------------


def _plot_token_growth(data: dict, out_dir: Path) -> None:
    by_regime: dict[str, list[list[int]]] = {}
    for c in data["cells"]:
        toks = [v["prompt_token_count"] for v in sorted(data["views"][c["cell_id"]], key=lambda v: v["iteration"])]
        if toks:
            by_regime.setdefault(c["regime"], []).append(toks)
    if not by_regime:
        return
    plt.figure(figsize=(7, 4))
    for regime, series in by_regime.items():
        width = max(len(s) for s in series)
        padded = np.array([s + [s[-1]] * (width - len(s)) for s in series], dtype=float)
        plt.plot(range(1, width + 1), padded.mean(axis=0), marker="o", label=regime)
    plt.xlabel("iteration"); plt.ylabel("prompt tokens (mean)")
    plt.title("Memory token growth per regime (SC-006)"); plt.legend()
    plt.tight_layout(); plt.savefig(out_dir / "token_growth.png", dpi=110); plt.close()


def _plot_paired_differences(comparisons: list[PairedComparison], out_dir: Path) -> None:
    valid = [c for c in comparisons if c.effect is not None]
    if not valid:
        return
    plt.figure(figsize=(7, 4))
    xs = range(len(valid))
    effects = [c.effect for c in valid]
    lows = [c.effect - (c.ci_low if c.ci_low is not None else c.effect) for c in valid]
    highs = [(c.ci_high if c.ci_high is not None else c.effect) - c.effect for c in valid]
    plt.bar(xs, effects, yerr=[lows, highs], capsize=6)
    plt.axhline(0, color="k", linewidth=0.8)
    plt.xticks(list(xs), [c.comparison for c in valid])
    plt.ylabel("relative effect (x vs y)"); plt.title("Paired comparisons (effect ± bootstrap CI)")
    plt.tight_layout(); plt.savefig(out_dir / "paired_differences.png", dpi=110); plt.close()


def _write_note(summary: dict, notes_dir: Path) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"<tr><td>{c['comparison']}</td><td>{c['hypothesis']}</td>"
        f"<td>{_fmt(c['effect'])}</td><td>[{_fmt(c['ci_low'])}, {_fmt(c['ci_high'])}]</td>"
        f"<td>{_fmt(c['p_value'])}</td><td>{c['test']}</td><td>{c['n_datasets']}</td></tr>"
        for c in summary["comparisons"]
    )
    html = (
        "<html><head><meta charset='utf-8'><title>Memory-Compaction Ablation</title></head><body>"
        "<h1>Memory-Compaction Ablation — results</h1>"
        f"<p>Cells analyzed: {len(summary['outcomes'])}. "
        "Regimes A=recent_only, B=all_raw, C=compacted_recent.</p>"
        "<h2>Paired comparisons (per-dataset, relative effect)</h2>"
        "<table border='1' cellpadding='4'><tr><th>comparison</th><th>hypothesis</th>"
        "<th>effect</th><th>95% CI</th><th>p</th><th>test</th><th>n</th></tr>"
        f"{rows}</table>"
        "<p>Plots: token_growth.png, paired_differences.png (under the analysis output dir).</p>"
        "</body></html>"
    )
    path = notes_dir / "ablation_results.html"
    path.write_text(html)
    return path


def _fmt(x: Any) -> str:
    return "n/a" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))


# ---------------------------------------------------------------------------
# Top-level analyze
# ---------------------------------------------------------------------------


def analyze(
    export_dir: str | Path, out_dir: str | Path, *,
    with_threshold_curves: bool = False, notes_dir: str | Path = "notes",
) -> dict[str, Any]:
    """Run the full analysis over an export and write outcomes/plots/note."""

    data = load_export(export_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    outcomes: list[OutcomeSummary] = []
    for c in data["cells"]:
        if c["status"] not in ("completed", "context_limited"):
            continue
        o = cell_outcome(c, data["records"][c["cell_id"]], data["views"][c["cell_id"]])
        if o is not None:
            outcomes.append(o)

    comparisons = paired_comparisons(outcomes)
    summary: dict[str, Any] = {
        "outcomes": [o.model_dump() for o in outcomes],
        "comparisons": [c.model_dump() for c in comparisons],
    }
    if with_threshold_curves:
        summary["threshold_curves"] = threshold_curves(outcomes)

    (out_dir / "outcomes.json").write_text(json.dumps(summary, indent=2))
    _plot_token_growth(data, out_dir)
    _plot_paired_differences(comparisons, out_dir)
    note = _write_note(summary, Path(notes_dir))
    summary["note_path"] = str(note)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a completed ablation export.")
    parser.add_argument("--from", dest="from_dir", default="outputs/export")
    parser.add_argument("--out", default="outputs/analysis")
    parser.add_argument("--threshold-curves", action="store_true")
    args = parser.parse_args()
    summary = analyze(args.from_dir, args.out, with_threshold_curves=args.threshold_curves)
    print(
        f"Analyzed {len(summary['outcomes'])} cells; "
        f"{len(summary['comparisons'])} comparisons. "
        f"Outputs -> {args.out}; note -> {summary['note_path']}"
    )


if __name__ == "__main__":
    main()
