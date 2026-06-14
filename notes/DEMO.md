# Interactive Demo — Autonomous Data-Scientist Loop

A copy-paste walkthrough you can read aloud while demoing, or run all at once with
[`scripts/demo.sh`](../scripts/demo.sh). Every command here runs **fully offline** — no
Vertex/Gemini credentials — by forcing the deterministic in-process agent with `STUB_LLM=1`.

> **The story in one line:** the loop runs the *same* experiment under different **memory
> regimes**, persists every decision as replayable evidence in Postgres, and then lets you
> **audit** that memory was the only thing that changed and that the compaction operator
> dropped no signal.

---

## 0. Prerequisites (once)

The only moving part is Postgres. If it isn't already up:

```bash
docker compose up -d db          # Postgres 17 on localhost:5432
```

Everything else uses `uv run`, which resolves the project venv automatically. The default
`DATABASE_URL` is `postgresql+psycopg://autods:autods@localhost:5432/autods`.

**Run the whole thing unattended:**

```bash
./scripts/demo.sh                # ~30s, prints a 5-step narrated trace
```

…or walk the steps by hand below.

---

## 1. Run an experiment — watch the loop iterate (offline)

`STUB_LLM=1` swaps in a deterministic agent (no network), so the loop materialises the
dataset, runs the baseline, and then iterates: seed → expand/train/score → next-step → record.

```bash
STUB_LLM=1 uv run ds-agent-loop --member wine --seed 0 \
    --regime compacted_recent --k 5 --m 3 --iterations 9
```

- `--member wine` — pick a dataset from the materialised benchmark suite (`wine`, `delivery_time`, …).
- `--regime` — the memory strategy (see step 2).
- `--k 5` — keep the last 5 experiment records in the prompt.
- `--m 3` — **compaction cadence**: summarise the trajectory into a Directional Research
  Memory artifact every 3 iterations.

Drop `STUB_LLM=1` to run it for real against Vertex/Gemini.

## 2. Run the SAME experiment under a different memory regime

The whole point of the harness is an apples-to-apples comparison: same data, same budget,
**only the memory differs**. Run the recent-only regime so we have a pair to compare.

```bash
STUB_LLM=1 uv run ds-agent-loop --member wine --seed 0 \
    --regime recent_only --k 5 --m 3 --iterations 9
```

The three regimes:

| Regime | What the agent sees each step |
|---|---|
| `all_raw` | the entire experiment history (tokens grow every iteration) |
| `recent_only` | only the last `k` records |
| `compacted_recent` | a compaction artifact **plus** the last `k` records |

## 3. Export the inspectable evidence

Pull everything out of Postgres into flat JSON/CSV you can open, diff, or commit.

```bash
uv run python -m ds_agent_loop.store export --out outputs/export
```

Look in `outputs/export/`: per-cell records, every iteration's decision, and
`artifacts.json` — each compaction artifact with its full **source → artifact lineage**.

## 4. Analyse — token growth and paired regime differences

```bash
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis
```

Produces `outputs/analysis/token_growth.png`, `paired_differences.png`, `outcomes.json`, and
a self-contained report at **`notes/ablation_results.html`** — open that in a browser when
demoing to a room.

## 5. Audit — prove memory was the only variable

The provenance CLI (`ds-agent-memory`) checks the recorded evidence **deterministically, with
zero LLM calls**.

**5a. Cross-regime audit** — confirm the two cells differ only in memory (same member, seed,
budget, split, allowlist → identical config fingerprint):

```bash
uv run ds-agent-memory audit \
    --cell-a 'wine|recent_only|s0|k5|m3' \
    --cell-b 'wine|compacted_recent|s0|k5|m3'
# [ok] ... fingerprint_equal=True ... valid memory-only comparison
```

**5b. Compaction lineage audit** — for each artifact, reconstruct from raw history the exact
set of records at/before its trigger and assert it equals the recorded sources. Fails loudly
if a future record leaked in or a past one was dropped:

```bash
uv run ds-agent-memory compaction 'wine|compacted_recent|s0|k5|m3'
# artifact ...@3: trigger=3 cadence=3 mode=fixed sources=3
# artifact ...@6: trigger=6 cadence=3 mode=fixed sources=6
# artifact ...@9: trigger=9 cadence=3 mode=fixed sources=9
# [ok] ... OK (3 artifacts, 0 LLM calls)
```

---

## Play around

- **More seeds / a sweep:** `STUB_LLM=1 uv run python entrypoint/run.py` runs the full
  configured ablation sweep offline (override scope with `SEEDS=0,1,2 DATASETS=wine REGIMES=recent_only,compacted_recent`).
- **Different dataset:** swap `--member wine` for `--member delivery_time`.
- **Tighter/looser compaction:** vary `--m` (cadence) and `--k` (memory tail).
- **Real LLM run:** drop `STUB_LLM=1` (needs `.env` Vertex config).

**5c. Verified replay** — re-derive each decision's memory view from persisted history and assert
it hashes byte-for-byte to what the agent was shown (no LLM calls). This is the per-decision
reproducibility proof:

```bash
uv run ds-agent-memory replay --cell 'wine|recent_only|s0|k5|m3'
# [ok] wine|recent_only|s0|k5|m3: matched 9/9
```

Replays the whole sweep at once with `--all`. (Replay is hash-exact only for cells recorded by the
current builder; cells recorded before the `memory.py` `sort_keys` rendering fix will report
spurious per-iteration mismatches — regenerate them.)

## Cell-id cheat sheet

Cells are addressed as `member|regime|s<seed>|k<k>|m<m>` — e.g.
`wine|compacted_recent|s0|k5|m3`. That's the id you pass to the `ds-agent-memory` audits.
