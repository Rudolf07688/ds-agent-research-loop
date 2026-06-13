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

from . import benchmark, compaction, data_gen, history, llm, memory, provenance
from . import store as store_mod
from .prompts import (
    CellStatus,
    ExperimentCell,
    ExperimentRecord,
    MemoryRegime,
    NextAction,
    NextStepDecision,
    RunRecord,
    Settings,
    TaskType,
)
from .train import (
    BASELINE_BY_TASK,
    BASELINE_MODEL,
    MODEL_ALLOWLIST,
    ValidationRejected,
    allowlist_for,
    score_model,
    score_on_split,
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


# ===========================================================================
# Feature 003: the parameterized cell runner (run_cell) — US1/US2
# ===========================================================================
#
# ``run_cell`` runs ONE (dataset × regime × seed × k × m) cell to budget: at each iteration
# it builds the regime-specific memory view (the sole manipulated variable, Principle XIII),
# persists it BEFORE the decision, scores the chosen model on the FROZEN split, and records
# a fully-provenanced ExperimentRecord. The agent call is injected (``propose``) so the loop
# is testable offline; the default uses the real Vertex/Gemini call.


def cell_id_for(dataset_id: str, regime: MemoryRegime, seed: int, k: int, m: int) -> str:
    """Deterministic, idempotent cell key from the factor tuple (FR-014)."""

    return f"{dataset_id}|{regime.value}|s{seed}|k{k}|m{m}"


def _is_better(new: float, best: float | None, direction: int) -> bool:
    """Direction-aware improvement test (+1 higher-is-better, -1 lower-is-better; FR-023)."""

    if best is None:
        return True
    return new > best if direction > 0 else new < best


def _apply_decision(
    decision: NextStepDecision, prev_model: str, prev_hp: dict
) -> tuple[str, dict]:
    """Map a validated decision to the (model, hyperparameters) to run. The benchmark
    dataset/split is fixed, so ``expand_dataset`` is a no-op that retains the model (the
    action space stays identical across regimes, Principle XIII)."""

    action = decision.action
    if action is NextAction.tune_hyperparameters:
        return prev_model, dict(decision.hyperparameters)
    if action is NextAction.switch_model:
        return decision.model_name, dict(decision.hyperparameters)
    if action is NextAction.keep_model:
        return decision.model_name or prev_model, dict(prev_hp)
    # expand_dataset / stop are handled by the caller; default retains the model.
    return prev_model, dict(prev_hp)


async def _default_propose(
    settings: Settings,
    *,
    memory_text: str,
    allowlist: list[str],
    best_summary: str,
    dataset_summary: str,
    metric: str,
    goal_word: str,
) -> NextStepDecision:
    """Default agent call — the real Vertex/Gemini structured next-step request."""

    return await llm.request_next_step_ablation(
        settings,
        memory_text=memory_text,
        allowlist=allowlist,
        best_summary=best_summary,
        dataset_summary=dataset_summary,
        metric=metric,
        goal_word=goal_word,
    )


async def run_cell(
    descriptor: benchmark.DatasetDescriptor,
    regime: MemoryRegime,
    seed: int,
    *,
    k: int,
    m: int,
    iterations: int,
    store: object,
    settings: Settings,
    state_dir: Path = STATE_DIR,
    propose=None,
    split=None,
    compactor=None,
    context_token_limit: int | None = None,
    compaction_token_threshold: int | None = None,
    repro: dict | None = None,
) -> ExperimentCell:
    """Run one ablation cell to budget; persist records, views and (regime C) artifacts.

    Resumable (SC-007): a terminal cell is returned untouched; a partially-run cell continues
    from its last recorded iteration. The exact memory view is persisted before each decision
    (FR-013); ``all_raw`` that exceeds ``context_token_limit`` stops the cell and records it
    ``context_limited`` (clarification 2026-06-13) rather than silently truncating.
    """

    propose = propose or _default_propose
    cid = cell_id_for(descriptor.dataset_id, regime, seed, k, m)
    log = store_mod.get_logger(store, cid)
    metric = descriptor.primary_metric
    direction = descriptor.metric_direction
    goal_word = "raise" if direction > 0 else "lower"
    allowlist = allowlist_for(descriptor.task_type)
    baseline = BASELINE_BY_TASK[descriptor.task_type]
    dataset_summary = f"{descriptor.dataset_id} ({descriptor.task_type.value}), {len(descriptor.feature_names)} features"

    # --- resume bookkeeping ---------------------------------------------------
    existing_cell = store.get_cell(cid)
    if existing_cell is not None and existing_cell.status in (
        CellStatus.completed,
        CellStatus.context_limited,
        CellStatus.failed,
    ):
        log.info("cell_skipped_terminal", status=existing_cell.status.value)
        return existing_cell

    # One regime / one k per cell for life (FR-012): a resume that changes the manipulated
    # variable would break the controlled comparison — fail loudly rather than silently diverge.
    if existing_cell is not None and (existing_cell.regime is not regime or existing_cell.k != k):
        raise ValueError(
            f"Cell '{cid}' was started under regime={existing_cell.regime.value} k={existing_cell.k}; "
            f"refusing to resume it under regime={regime.value} k={k} (memory is the controlled variable)."
        )

    history_records: list[ExperimentRecord] = store.get_records(cid)
    best_primary: float | None = None
    best_model = "none"
    for r in history_records:
        val = (r.test_metrics or r.metrics).get(metric)
        if val is not None and _is_better(val, best_primary, direction):
            best_primary, best_model = val, r.model_name
    prev_model = baseline
    prev_hp: dict = {}
    if history_records:
        last = history_records[-1]
        prev_model = last.executed_config.get("model_name", baseline)
        prev_hp = dict(last.executed_config.get("hyperparameters", {}))
    start_iter = len(history_records) + 1

    dataset = benchmark.load_dataset(descriptor.dataset_id)
    # The frozen split is resolved from the materialized suite by the orchestrator (US4) and
    # injected; fall back to the on-disk computation when run directly (offline tests).
    if split is None:
        split = benchmark.frozen_split(descriptor.dataset_id, state_dir=state_dir)

    repro_stamp = {
        "benchmark_version": descriptor.benchmark_version,
        "split_ref": descriptor.split_ref,
        "seed": seed,
        "regime": regime.value,
        "k": k,
        "m": m,
        **(repro or {}),
    }
    cell = ExperimentCell(
        cell_id=cid, dataset_id=descriptor.dataset_id, regime=regime, seed=seed,
        k=k, m=m, budget=iterations, status=CellStatus.running, repro=repro_stamp,
        last_iteration=len(history_records) or None,
        created_ts=existing_cell.created_ts if existing_cell else None,
    )
    # Stamp the held-fixed-factor fingerprint (excludes regime/k/memory) so the cross-regime audit
    # can prove memory was the only variable for this (member, seed) (FR-010; provenance.py).
    repro_stamp["config_fingerprint"] = provenance.config_fingerprint(cell, descriptor)
    cell = cell.model_copy(update={"repro": repro_stamp})
    store.upsert_cell(cell)
    if start_iter <= iterations:
        log.info("cell_started", regime=regime.value, seed=seed, k=k, m=m, budget=iterations, resume_from=start_iter)

    status = CellStatus.completed
    # The ablation cell is budget-governed: it runs the full N iterations so that the ONLY thing
    # differing across regimes is the memory view (SC-002), never the iteration count. The member's
    # `patience` is a persisted/enforced fixed factor used by the descriptor-driven toy loop
    # (`run_loop`); here we record which terminal condition stopped the cell (FR-016).
    stop_reason = "budget"
    action_space = set(descriptor.action_space)
    latest_artifact = store.latest_artifact(cid)

    for i in range(start_iter, iterations + 1):
        view = memory.build_view(
            regime, history_records, k=k, cell_id=cid, iteration=i, latest_artifact=latest_artifact
        )
        # all_raw context-limit guard (clarification 2026-06-13): stop, record context_limited.
        if context_token_limit is not None and view.prompt_token_count > context_token_limit:
            status = CellStatus.context_limited
            stop_reason = "context_limited"
            log.warning(
                "context_limited", iteration=i,
                prompt_token_count=view.prompt_token_count, limit=context_token_limit,
                remaining_budget=iterations - (i - 1),
            )
            break

        proposal: NextStepDecision | None = None
        rejected = False
        if i == 1:
            model, hp, rationale = baseline, {}, "baseline (first iteration)"
        else:
            best_summary = f"{best_model} {metric}={best_primary:.4f}" if best_primary is not None else "none yet"
            decision = await propose(
                settings, memory_text=view.rendered_text, allowlist=list(allowlist),
                best_summary=best_summary, dataset_summary=dataset_summary,
                metric=metric, goal_word=goal_word,
            )
            if decision.action is NextAction.stop:
                log.info("agent_stop", iteration=i, reason=decision.reason)
                status = CellStatus.completed
                stop_reason = "agent_stop"
                break
            proposal = decision
            # Bounded agency (FR-016): the member's frozen action space is enforced — an action
            # outside it is rejected before training, like an out-of-allowlist model.
            if decision.action.value not in action_space:
                rejected = True
                model, hp = prev_model, dict(prev_hp)
                rationale = (
                    f"REJECTED action '{decision.action.value}' not in frozen action_space "
                    f"{sorted(action_space)}; retained {prev_model}."
                )
                log.warning(
                    "proposal_rejected", iteration=i, action=decision.action.value,
                    reason="action not in frozen action_space",
                )
            else:
                try:
                    validate_decision(decision, prev_model, allowlist)
                except ValidationRejected as exc:
                    rejected = True
                    model, hp = prev_model, dict(prev_hp)
                    rationale = f"REJECTED proposal; retained {prev_model}. {exc}"
                    log.warning("proposal_rejected", iteration=i, reason=str(exc), action=decision.action.value)
                else:
                    model, hp = _apply_decision(decision, prev_model, prev_hp)
                    rationale = decision.reason or f"applied {decision.action.value}"

        store.save_view(view)  # exact memory shown, persisted BEFORE the decision is recorded
        val_metrics, test_metrics = score_on_split(
            dataset, feature_schema=descriptor.feature_schema, target=descriptor.target,
            task_type=descriptor.task_type, split=split, model_name=model,
            hyperparameters=hp, allowlist=allowlist,
        )
        primary = test_metrics[metric]
        improved = _is_better(primary, best_primary, direction)
        if improved:
            best_primary, best_model = primary, model

        record = ExperimentRecord(
            iteration=i, dataset_size=len(dataset), model_name=model, hyperparameters=hp,
            metrics=test_metrics, rationale=rationale, timestamp=_now(),
            cell_id=cid, dataset_id=descriptor.dataset_id, regime=regime, seed=seed, k=k, m=m,
            proposal=proposal, executed_config={"model_name": model, "hyperparameters": hp},
            val_metrics=val_metrics, test_metrics=test_metrics, improved=improved,
            rejected=rejected, memory_view_ref=view.content_hash,
        )
        store.append_record(record)
        history_records.append(record)
        log.info(
            "iteration_done", iteration=i, model=model, **{metric: round(primary, 4)},
            improved=improved, rejected=rejected, prompt_token_count=view.prompt_token_count,
            included_records=len(view.included_record_ids), memory_view_ref=view.content_hash,
        )
        prev_model, prev_hp = model, hp

        # --- outer compaction loop (regime C) — Principle XII ----------------
        if (
            regime is MemoryRegime.compacted_recent
            and compactor is not None
            and compaction.should_compact(
                i, m, prompt_tokens=view.prompt_token_count,
                token_threshold=compaction_token_threshold,
            )
        ):
            source = compaction.select_source(history_records, i)  # at/before trigger only (SC-005)
            trigger_mode = compaction.trigger_mode_for(
                i, m, len(source),
                prompt_tokens=view.prompt_token_count,
                token_threshold=compaction_token_threshold,
            )
            artifact_dict = await compactor(
                settings, source_records=source, descriptor=descriptor
            )
            store.save_artifact(
                cell_id=cid, trigger_iteration=i, artifact=artifact_dict,
                source_record_ids=[r.iteration for r in source],
                cadence=m, trigger_mode=trigger_mode,
            )
            latest_artifact = store.latest_artifact(cid)
            log.info(
                "compaction_done", iteration=i, source_records=len(source),
                cadence=m, mode=trigger_mode,
            )

    repro_stamp = {**repro_stamp, "stop_reason": stop_reason}
    cell = cell.model_copy(
        update={"status": status, "last_iteration": len(history_records), "repro": repro_stamp}
    )
    store.upsert_cell(cell)
    log.info("cell_finished", status=status.value, iterations=len(history_records),
             best_metric=metric, best_value=best_primary)
    return cell


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
    parser = argparse.ArgumentParser(
        description="Run ONE memory-regime ablation cell (dataset × regime × seed × k × m)."
    )
    parser.add_argument(
        "--member", "--dataset", dest="dataset", required=True,
        help="benchmark member id, e.g. wine (alias: --dataset)",
    )
    parser.add_argument(
        "--regime", default=settings.regime.value,
        choices=[r.value for r in MemoryRegime],
        help="memory regime (the manipulated variable); defaults to Settings.regime / REGIME",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--k", type=int, default=settings.recent_k)
    parser.add_argument("--m", type=int, default=settings.compaction_m)
    parser.add_argument("--iterations", type=int, default=settings.n_iterations)
    parser.add_argument(
        "--context-token-limit", type=int, default=None,
        help="optional: stop all_raw and mark context_limited above this many memory tokens",
    )
    return parser.parse_args()


async def _run_single_cell(args: argparse.Namespace, settings: Settings) -> ExperimentCell:
    """Build the store + descriptor and run one cell (contracts/runner-cli.md §Single cell).

    Condition C wires the real compaction operator so a single ``compacted_recent`` cell
    generates Directional Research Memory at its cadence.
    """

    store_mod.upgrade_to_head(settings.database_url)  # schema owned by Alembic (Principle IV)
    engine = store_mod.make_engine(settings.database_url)
    store = store_mod.Store(engine)
    # Resolve the member from the materialized, versioned suite (US4): no delivery-time-specific
    # path — the descriptor, frozen split, allowlist, action space and budget all come from the
    # persisted member, loaded by id.
    benchmark.materialize_suite(store, [args.dataset], version=settings.benchmark_version)
    descriptor, split, _ = benchmark.load_member(store, args.dataset, version=settings.benchmark_version)
    regime = MemoryRegime(args.regime)
    compactor = compaction.compact if regime is MemoryRegime.compacted_recent else None
    return await run_cell(
        descriptor, regime, args.seed,
        k=args.k, m=args.m, iterations=args.iterations,
        store=store, settings=settings, state_dir=STATE_DIR,
        split=split, compactor=compactor, context_token_limit=args.context_token_limit,
        compaction_token_threshold=settings.compaction_token_threshold,
    )


def main() -> None:
    settings = Settings()
    args = _parse_args(settings)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    cell = asyncio.run(_run_single_cell(args, settings))
    print(
        f"Done. cell={cell.cell_id} status={cell.status.value} "
        f"iterations={cell.last_iteration}. State persisted to Postgres "
        f"({settings.database_url.split('@')[-1]}); export with "
        f"`python -m ds_agent_loop.store export`."
    )


if __name__ == "__main__":
    main()
