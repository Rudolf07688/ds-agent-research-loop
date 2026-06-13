"""The experiment loop: seed -> expand -> train/score -> next-step -> record.

``main.py`` is the only orchestrator (Constitution Principle I). It wires together the
single-purpose modules, starts from the ``LinearRegression`` baseline (FR-005a), applies
the LLM's validated next-step decision, and stops after ``N`` iterations or after
``patience`` consecutive rounds without RMSE improvement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import data_gen, history, llm
from .prompts import NextAction, NextStepDecision, RunRecord, Settings
from .train import (
    BASELINE_MODEL,
    MODEL_ALLOWLIST,
    ValidationRejected,
    score_model,
    validate_decision,
)

STATE_DIR = Path("state")
OUTPUTS_DIR = Path("outputs")
SUMMARY_FILE = "run_summary.txt"

# How many rows to add when the LLM chooses to expand the dataset.
EXPAND_STEP = 250


# ---------------------------------------------------------------------------
# Pure decision dispatch + stop logic (testable without an LLM) — G1, US4/US5
# ---------------------------------------------------------------------------


@dataclass
class StepPlan:
    """The concrete next step to apply after a validated decision."""

    model_name: str
    hyperparameters: dict = field(default_factory=dict)
    expand_to: int | None = None
    stop: bool = False


def decide_next(
    decision: NextStepDecision,
    *,
    current_model: str,
    current_hp: dict,
    current_size: int,
) -> tuple[StepPlan, bool, str]:
    """Validate + dispatch a decision into a StepPlan.

    Returns ``(plan, rejected, reason)``. On any validation failure the proposal is
    rejected and the returned plan retains the prior model/hyperparameters (FR-016a) —
    LLM-supplied content is never executed.
    """

    try:
        validate_decision(decision, current_model)
    except ValidationRejected as exc:
        return StepPlan(current_model, dict(current_hp)), True, str(exc)

    action = decision.action
    if action is NextAction.stop:
        return StepPlan(current_model, dict(current_hp), stop=True), False, decision.reason
    if action is NextAction.expand_dataset:
        return (
            StepPlan(current_model, dict(current_hp), expand_to=current_size + EXPAND_STEP),
            False,
            decision.reason,
        )
    if action is NextAction.tune_hyperparameters:
        return StepPlan(current_model, dict(decision.hyperparameters)), False, decision.reason
    if action is NextAction.switch_model:
        return StepPlan(decision.model_name, dict(decision.hyperparameters)), False, decision.reason
    # keep_model
    model = decision.model_name or current_model
    return StepPlan(model, dict(current_hp)), False, decision.reason


def should_stop(no_improvement_rounds: int, patience: int) -> bool:
    """Stop early after ``patience`` consecutive rounds without RMSE improvement."""

    return no_improvement_rounds >= patience


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _best_summary(best: RunRecord | None) -> str:
    if best is None:
        return "none yet"
    return f"{best.model_name} rmse={best.metrics['rmse']:.3f} (iter {best.iteration})"


async def run_loop(settings: Settings, state_dir: Path, outputs_dir: Path) -> None:
    seed_rows, spec = await data_gen.bootstrap_seed(settings, state_dir)
    dataset = data_gen.expand_dataset(
        spec, settings.target_size, seed_rows=seed_rows, state_dir=state_dir
    )

    current_model = BASELINE_MODEL
    current_hp: dict = {}
    rationale = "Baseline LinearRegression (first iteration)."
    best = history.load_best_run(state_dir)
    no_improvement = 0
    stop_reason = "completed all iterations"

    for iteration in range(1, settings.n_iterations + 1):
        metrics = score_model(dataset, current_model, current_hp)
        record = RunRecord(
            iteration=iteration,
            dataset_size=len(dataset),
            model_name=current_model,
            hyperparameters=current_hp,
            metrics=metrics,
            rationale=rationale,
            timestamp=_now(),
        )
        hist = history.append_run(record, state_dir)
        best, improved = history.update_best_run(record, state_dir)
        no_improvement = 0 if improved else no_improvement + 1
        print(
            f"[iter {iteration}] {current_model} rmse={metrics['rmse']:.3f} "
            f"r2={metrics['r2']:.3f} (best {best.metrics['rmse']:.3f})"
        )

        if should_stop(no_improvement, settings.patience):
            stop_reason = f"no RMSE improvement for {settings.patience} rounds"
            break
        if iteration == settings.n_iterations:
            break

        history_json = json.dumps([r.model_dump() for r in hist[-8:]], indent=2)
        try:
            decision = await llm.request_next_step(
                settings,
                history_json=history_json,
                allowlist=list(MODEL_ALLOWLIST),
                best_summary=_best_summary(best),
            )
        except llm.LLMError as exc:
            stop_reason = f"LLM next-step call failed: {exc}"
            break

        plan, rejected, reason = decide_next(
            decision,
            current_model=current_model,
            current_hp=current_hp,
            current_size=len(dataset),
        )
        if rejected:
            history.record_rejection(
                iteration=iteration,
                dataset_size=len(dataset),
                current_model=current_model,
                retained_metrics=metrics,
                reason=reason,
                timestamp=_now(),
                state_dir=state_dir,
            )
            print(f"  proposal rejected ({reason}); retaining {current_model}")
            rationale = f"Retained {current_model} after rejected proposal."
            continue
        if plan.stop:
            stop_reason = f"LLM requested stop: {reason}"
            break
        if plan.expand_to is not None:
            dataset = data_gen.expand_dataset(
                spec, plan.expand_to, seed_rows=seed_rows, state_dir=state_dir
            )
        current_model = plan.model_name
        current_hp = plan.hyperparameters
        rationale = reason or f"Applied {decision.action.value}."

    _write_summary(outputs_dir, best, history.load_history(state_dir), stop_reason)


def _write_summary(
    outputs_dir: Path, best: RunRecord | None, hist: list[RunRecord], stop_reason: str
) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    lines = ["LLM Autonomous Data Scientist (Toy) — run summary", "=" * 50, ""]
    lines.append(f"Iterations recorded : {len(hist)}")
    lines.append(f"Stop reason         : {stop_reason}")
    if best is not None:
        lines.append("")
        lines.append("Best run:")
        lines.append(f"  iteration   : {best.iteration}")
        lines.append(f"  model       : {best.model_name}")
        lines.append(f"  hyperparams : {best.hyperparameters}")
        lines.append(f"  dataset_size: {best.dataset_size}")
        lines.append(f"  rmse        : {best.metrics.get('rmse'):.4f}")
        if "r2" in best.metrics:
            lines.append(f"  r2          : {best.metrics['r2']:.4f}")
        if "mae" in best.metrics:
            lines.append(f"  mae         : {best.metrics['mae']:.4f}")
    (outputs_dir / SUMMARY_FILE).write_text("\n".join(lines) + "\n")


def _parse_args(settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the toy AutoDS loop.")
    parser.add_argument("--iterations", type=int, default=settings.n_iterations)
    parser.add_argument("--patience", type=int, default=settings.patience)
    parser.add_argument("--target-size", type=int, default=settings.target_size)
    parser.add_argument("--metric", default=settings.primary_metric, choices=["rmse"])
    return parser.parse_args()


def main() -> None:
    settings = Settings()
    args = _parse_args(settings)
    settings = settings.model_copy(
        update={
            "n_iterations": args.iterations,
            "patience": args.patience,
            "target_size": args.target_size,
            "primary_metric": args.metric,
        }
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(run_loop(settings, STATE_DIR, OUTPUTS_DIR))
    print(f"Done. See {OUTPUTS_DIR / SUMMARY_FILE} and state/.")


if __name__ == "__main__":
    main()
