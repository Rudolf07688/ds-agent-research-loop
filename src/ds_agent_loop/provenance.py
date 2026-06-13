"""Decision-provenance verification: replay, config fingerprint, cross-regime audit.

Feature 005 (Principles IX & XIII). This module is the *verifier* counterpart to ``memory.py``
(the *builder* seam): it never constructs a new view from scratch — it re-invokes
``memory.build_view`` so that "what we rebuild" and "what the agent was shown" are produced by
identical code, which is the only way their content hashes can match.

All functions here are PURE and make NO LLM calls (Principle IX): they read only persisted state
(records, views, artifacts, members) via the ``store`` interface. Failures are loud and specific
(Principle X). Nothing here is invoked from the loop run path — verification is on demand only
(clarification 2026-06-13; contracts/provenance-api.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

from . import benchmark, memory
from . import store as store_mod
from .benchmark import DatasetDescriptor
from .prompts import (
    AuditResult,
    ExperimentCell,
    ExperimentRecord,
    ReplayMismatch,
    ReplayResult,
    Settings,
)

# A literal marker for the fixed prompt/schema contract. It is part of the held-fixed factors so a
# silent change to the per-iteration agent contract would change the fingerprint and be caught by
# the cross-regime audit (FR-010).
PROMPT_SCHEMA_VERSION = "next_step_ablation_v1"


# ---------------------------------------------------------------------------
# Verified replay (FR-008/009, US3)
# ---------------------------------------------------------------------------


def replay_view(
    record: ExperimentRecord,
    history_before: list[ExperimentRecord],
    *,
    artifact: dict | None = None,
) -> ReplayMismatch | None:
    """Rebuild the memory view for ``record`` and compare it to what was persisted.

    ``history_before`` MUST be the records of this cell with ``iteration < record.iteration`` (the
    exact slice the agent saw at decision time). Returns ``None`` when the rebuilt content hash
    equals ``record.memory_view_ref``, else a :class:`ReplayMismatch`. No LLM calls (FR-008).
    """

    rebuilt = memory.build_view(
        record.regime,
        history_before,
        k=record.k or 0,
        cell_id=record.cell_id or "",
        iteration=record.iteration,
        latest_artifact=artifact,
    )
    if rebuilt.content_hash == record.memory_view_ref:
        return None
    return ReplayMismatch(
        iteration=record.iteration,
        expected_hash=record.memory_view_ref or "",
        actual_hash=rebuilt.content_hash,
    )


def _artifact_before(artifacts: list[dict[str, Any]], iteration: int) -> dict | None:
    """The compaction artifact in effect at ``iteration`` — the most recent one triggered strictly
    before it (compaction runs at the end of an iteration, so iteration i sees triggers < i)."""

    eligible = [a for a in artifacts if a["trigger_iteration"] < iteration]
    return eligible[-1] if eligible else None


def verify_cell(store: Any, cell_id: str) -> ReplayResult:
    """Replay every recorded decision of ``cell_id`` and assert hash equality (US3, FR-008/009).

    Reads only persisted state; performs no LLM calls. ``ReplayResult.ok`` is True iff every
    decision's rebuilt view matches the persisted hash; mismatches name their iterations (loud
    failure, Principle X).
    """

    records = store.get_records(cell_id)
    artifacts = store.get_artifacts(cell_id)
    result = ReplayResult(cell_id=cell_id, total=len(records))
    for rec in records:
        history_before = [r for r in records if r.iteration < rec.iteration]
        artifact = _artifact_before(artifacts, rec.iteration)
        mismatch = replay_view(rec, history_before, artifact=artifact)
        if mismatch is None:
            result.matched += 1
        else:
            result.mismatches.append(mismatch)
    return result


# ---------------------------------------------------------------------------
# Config fingerprint (FR-010) — the held-fixed factors, EXCLUDING regime/k/memory
# ---------------------------------------------------------------------------


def _held_fixed_factors(cell: ExperimentCell, descriptor: DatasetDescriptor) -> dict[str, Any]:
    """Every factor that MUST be identical across regimes for a fixed (member, seed). Excludes
    ``regime``, ``k`` (memory-tail size), and all memory content (FR-010, research Decision 2)."""

    return {
        "prompt_schema": PROMPT_SCHEMA_VERSION,
        "dataset_id": descriptor.dataset_id,
        "benchmark_version": descriptor.benchmark_version,
        "split_ref": descriptor.split_ref,
        "task_type": descriptor.task_type.value,
        "target": descriptor.target,
        "feature_schema": descriptor.feature_schema,
        "primary_metric": descriptor.primary_metric,
        "metric_direction": descriptor.metric_direction,
        "budget": cell.budget,
        "patience": descriptor.patience,
        "action_space": sorted(descriptor.action_space),
        "model_allowlist": sorted(descriptor.model_allowlist),
        "seed": cell.seed,
    }


def config_fingerprint(cell: ExperimentCell, descriptor: DatasetDescriptor) -> str:
    """SHA-256 over the canonicalized held-fixed factors (sorted keys). Deterministic and
    order-independent; the equality token for the cross-regime audit (FR-010)."""

    payload = json.dumps(_held_fixed_factors(cell, descriptor), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cross-regime audit (FR-011, US4) — memory is the only variable
# ---------------------------------------------------------------------------


def _descriptor_for_cell(store: Any, cell: ExperimentCell) -> DatasetDescriptor:
    version = cell.repro.get("benchmark_version") or benchmark.BENCHMARK_VERSION
    descriptor, _split, _df = benchmark.load_member(store, cell.dataset_id, version=version)
    return descriptor


def audit_regimes(store: Any, cell_id_a: str, cell_id_b: str) -> AuditResult:
    """Audit two cells as a memory-only comparison (US4, FR-011).

    Gates on same ``(member, seed)``; asserts equal :func:`config_fingerprint`, naming the first
    differing held-fixed factor on mismatch; on success reports the regime/``k`` difference as the
    intended dimension. ``AuditResult.ok`` is True iff the pair is a valid, uncontaminated
    memory-only comparison.
    """

    cell_a = store.get_cell(cell_id_a)
    cell_b = store.get_cell(cell_id_b)
    if cell_a is None or cell_b is None:
        missing = cell_id_a if cell_a is None else cell_id_b
        raise KeyError(f"Cell '{missing}' not found in store.")

    same = cell_a.dataset_id == cell_b.dataset_id and cell_a.seed == cell_b.seed
    if not same:
        return AuditResult(
            cell_a=cell_id_a, cell_b=cell_id_b, same_member_seed=False,
            reason="not a memory-only comparison: cells differ in (member, seed)",
        )

    desc_a = _descriptor_for_cell(store, cell_a)
    desc_b = _descriptor_for_cell(store, cell_b)
    factors_a = _held_fixed_factors(cell_a, desc_a)
    factors_b = _held_fixed_factors(cell_b, desc_b)
    fp_equal = config_fingerprint(cell_a, desc_a) == config_fingerprint(cell_b, desc_b)

    differing_factor = None
    if not fp_equal:
        for key in factors_a:
            if factors_a[key] != factors_b.get(key):
                differing_factor = key
                break

    dim = f"regime: {cell_a.regime.value} -> {cell_b.regime.value}"
    if cell_a.k != cell_b.k:
        dim += f", k: {cell_a.k} -> {cell_b.k}"

    reason = (
        f"contaminated: held-fixed factor '{differing_factor}' differs"
        if not fp_equal
        else "valid memory-only comparison"
    )
    return AuditResult(
        cell_a=cell_id_a, cell_b=cell_id_b, same_member_seed=True,
        fingerprint_equal=fp_equal, differing_factor=differing_factor,
        differing_dimension=dim, reason=reason,
    )


# ---------------------------------------------------------------------------
# CLI (FR-017): `ds-agent-memory replay|audit` — on demand only
# ---------------------------------------------------------------------------


def _print_replay(result: ReplayResult) -> None:
    flag = "ok" if result.ok else "FAIL"
    print(f"[{flag}] {result.cell_id}: matched {result.matched}/{result.total}")
    for mm in result.mismatches:
        print(f"    iteration {mm.iteration}: expected {mm.expected_hash[:12]} got {mm.actual_hash[:12]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ds-agent-memory",
        description="Verify decision provenance: replay views and audit regimes (no LLM calls).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("replay", help="verify a cell's decisions are replayable (hash equality)")
    grp = rep.add_mutually_exclusive_group(required=True)
    grp.add_argument("--cell", help="cell_id to verify")
    grp.add_argument("--all", action="store_true", help="verify every cell in the store")

    aud = sub.add_parser("audit", help="audit two cells as a memory-only comparison")
    aud.add_argument("--cell-a", required=True)
    aud.add_argument("--cell-b", required=True)

    args = parser.parse_args(argv)
    settings = Settings()
    store_mod.upgrade_to_head(settings.database_url)  # schema owned by Alembic (Principle IV)
    store = store_mod.Store(store_mod.make_engine(settings.database_url))

    if args.command == "replay":
        cells = store.all_cells() if args.all else [store.get_cell(args.cell)]
        if not args.all and cells[0] is None:
            print(f"Cell '{args.cell}' not found.", file=sys.stderr)
            return 1
        results = [verify_cell(store, c.cell_id) for c in cells]
        for r in results:
            _print_replay(r)
        return 0 if all(r.ok for r in results) else 1

    # audit
    result = audit_regimes(store, args.cell_a, args.cell_b)
    flag = "ok" if result.ok else "FAIL"
    print(
        f"[{flag}] {result.cell_a} vs {result.cell_b}: "
        f"same_member_seed={result.same_member_seed} fingerprint_equal={result.fingerprint_equal}"
    )
    print(f"    dimension: {result.differing_dimension or '(n/a)'}")
    print(f"    {result.reason}")
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
