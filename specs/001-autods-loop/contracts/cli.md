# CLI / Run Contract

The only external interface is the command that runs the experiment loop (`main.py`).
It is a single-user, offline tool.

## Invocation

```text
uv run python main.py [--iterations N] [--patience K] [--target-size SIZE] [--metric rmse]
```

| Arg              | Type | Default | Meaning                                          |
|------------------|------|---------|--------------------------------------------------|
| `--iterations`   | int  | 10      | Number of loop iterations (`N`).                 |
| `--patience`     | int  | 3       | Stop after `K` consecutive rounds w/o improvement.|
| `--target-size`  | int  | 500     | Target dataset row count for local expansion.    |
| `--metric`       | enum | `rmse`  | Primary acceptance metric.                       |

All arguments are optional; defaults give a complete toy run.

## Preconditions

- A local `.env` provides LLM credentials and model name (see `.env.example`).
- `state/` and `outputs/` directories exist or are created on first run.

## Behavior (per the spec)

1. If `state/seed_rows.json` and `state/data_spec.json` are absent/invalid → one LLM
   seed-generation call (conforming to `seed_generation.schema.json`); persist both.
   Otherwise reuse existing state (no LLM call).
2. Expand `state/dataset.csv` toward `--target-size` locally from the saved data spec.
3. Train and score one candidate regressor on the primary metric.
4. Request a next-step decision (conforming to `next_step.schema.json`); validate
   `action` ∈ enum, `model_name` ∈ allowlist, and hyperparameters before any training.
5. Append the run to `state/history.json`; update `state/best_run.json` if improved.
6. Repeat until `--iterations` reached or no improvement for `--patience` rounds.

## Outputs

- Updated files under `state/` (`dataset.csv`, `history.json`, `best_run.json`).
- A human-readable `outputs/run_summary.txt` describing the run outcome.

## Exit conditions / errors

- Exit 0 on normal completion (iterations exhausted, patience reached, or LLM `stop`).
- Non-zero exit with a clear message on: malformed/invalid LLM output, out-of-allowlist
  model, invalid hyperparameters, or an unreadable required state file.
- The tool never executes LLM-supplied code; rejected proposals abort the iteration with
  a clear error rather than running.
