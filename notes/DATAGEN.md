# Data Generation — User Guide

Grow a synthetic dataset incrementally, always split **60% train / 20% val / 20% test**.
Fully offline and reproducible: rows are generated in pure Python from a saved spec
(Gaussian-copula features + an anchored target — see [`datagen_stats.md`](./datagen_stats.md)).

Files live in `state/`: `data_spec.json` (the recipe) and append-only `train.csv` /
`val.csv` / `test.csv`. Each `add` appends a fresh batch; existing rows never change partition.

## One-time setup

Only needed on a clean checkout with no `state/data_spec.json` (this step uses the LLM and
needs Vertex credentials):

```bash
uv run ds-agent-data bootstrap
```

## Add data

```bash
uv run ds-agent-data add -n 500     # append 500 rows -> +300 train / +100 val / +100 test
uv run ds-agent-data status         # show running totals and realized fractions
```

Re-run `add` as often as you like — the split stays exactly 60/20/20 and batch size doesn't
affect the final distribution. Each run adds *distinct* rows; a fixed `--seed` + starting
state reproduces the same sequence.

## Grow to a target (the loop)

To keep going until you have enough, use the helper script — it batches up to a target total,
lands exactly on it, and is a no-op if already there:

```bash
uv run python scripts/grow_dataset.py --target 5000               # default batch 500
uv run python scripts/grow_dataset.py --target 5000 --batch 1000 --seed 7
```

## Options

| Flag | Applies to | Meaning |
|------|-----------|---------|
| `-n / --count` | `add` | rows to append this run |
| `-t / --target` | `grow_dataset.py` | desired total row count |
| `-b / --batch` | `grow_dataset.py` | rows per batch (default 500) |
| `--seed` | both | base RNG seed (default 0) |
| `--state-dir` | both | build the dataset somewhere other than `state/` |

> **Scope:** this is the *expandable* synthetic dataset. The fixed, versioned **benchmark
> suite** used by the ablation (`ds-agent-loop`) is separate and deliberately not grown.
