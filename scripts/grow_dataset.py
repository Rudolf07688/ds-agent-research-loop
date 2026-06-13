#!/usr/bin/env python
"""Grow the synthetic dataset to a target size, in batches, split 60/20/20.

Thin wrapper around ``ds_agent_loop.data_gen``: repeatedly appends batches of rows
(each split into the append-only state/{train,val,test}.csv files) until the total
reaches ``--target``. Fully offline — derives every row from the saved
``state/data_spec.json`` (run ``ds-agent-data bootstrap`` once if you don't have one).

Examples:
    uv run python scripts/grow_dataset.py --target 5000
    uv run python scripts/grow_dataset.py --target 5000 --batch 1000 --seed 7
    uv run python scripts/grow_dataset.py --target 2000 --state-dir /tmp/mydata
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ds_agent_loop import data_gen


def _print_status(state_dir: Path) -> int:
    status = data_gen.data_status(state_dir)
    counts, fr = status["counts"], status["fractions"]
    print(
        f"  totals: train={counts['train']} ({fr['train']:.0%}), "
        f"val={counts['val']} ({fr['val']:.0%}), "
        f"test={counts['test']} ({fr['test']:.0%}) — {status['total']} rows."
    )
    return int(status["total"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grow the synthetic dataset to --target rows, in --batch increments "
        "(60/20/20 train/val/test, append-only).",
    )
    parser.add_argument("--target", "-t", type=int, required=True, help="desired total row count")
    parser.add_argument("--batch", "-b", type=int, default=500, help="rows per batch (default: 500)")
    parser.add_argument("--seed", type=int, default=0, help="base RNG seed (default: 0)")
    parser.add_argument(
        "--state-dir", default=str(data_gen.STATE_DIR), help="where the split files live"
    )
    args = parser.parse_args()

    if args.target <= 0:
        raise SystemExit("--target must be positive.")
    if args.batch <= 0:
        raise SystemExit("--batch must be positive.")

    state_dir = Path(args.state_dir)
    total = sum(data_gen._split_counts(state_dir).values())
    if total >= args.target:
        print(f"Already at {total} rows (>= target {args.target}); nothing to do.")
        _print_status(state_dir)
        return

    print(f"Growing {state_dir}/ from {total} to >= {args.target} rows in batches of {args.batch}...")
    while total < args.target:
        n = min(args.batch, args.target - total)  # don't overshoot the target
        try:
            added = data_gen.add_records(n, state_dir=state_dir, seed=args.seed)
        except data_gen.StateError as exc:
            raise SystemExit(
                f"{exc}\nRun `ds-agent-data --state-dir {state_dir} bootstrap` first."
            ) from exc
        print(f"+ {sum(added.values())} rows (train +{added['train']}, val +{added['val']}, test +{added['test']})")
        total = _print_status(state_dir)

    print(f"Done — reached {total} rows.")


if __name__ == "__main__":
    main()
