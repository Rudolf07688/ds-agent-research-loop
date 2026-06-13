#!/usr/bin/env bash
#
# demo.sh — end-to-end, OFFLINE demo of the autonomous-data-scientist loop.
#
# Runs the whole story with NO Vertex/Gemini credentials by forcing the
# deterministic in-process agent (STUB_LLM=1): generate data + run experiments
# across memory regimes, export the inspectable evidence, analyse it, and then
# prove the audit trail with the provenance CLI.
#
# Prereqs: Postgres reachable at DATABASE_URL (default
# postgresql+psycopg://autods:autods@localhost:5432/autods). If it isn't up:
#     docker compose up -d db
#
# Usage:
#     ./scripts/demo.sh                  # default: wine, seed 0, regimes recent_only + compacted_recent
#     MEMBER=wine SEED=0 ITERS=9 M=3 ./scripts/demo.sh
#
# Everything it writes lands under outputs/ and notes/ — safe to re-run.

set -euo pipefail
cd "$(dirname "$0")/.."

export STUB_LLM=1                      # offline, deterministic — no network, no credentials

MEMBER="${MEMBER:-wine}"
SEED="${SEED:-0}"
ITERS="${ITERS:-9}"                    # iterations per cell
K="${K:-5}"                            # recent-memory tail size
M="${M:-3}"                            # compaction cadence (compact every M iterations)

bar()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
note() { printf '    \033[2m%s\033[0m\n' "$*"; }

bar "[1/5] Two experiment cells — SAME data & budget, only the MEMORY differs (offline stub agent)"
note "recent_only keeps the last K=$K records; compacted_recent adds a Directional Research Memory artifact every M=$M iters."
for REGIME in recent_only compacted_recent; do
  note "running $MEMBER | $REGIME | seed $SEED | k$K m$M | $ITERS iterations ..."
  uv run ds-agent-loop --member "$MEMBER" --seed "$SEED" --regime "$REGIME" \
      --k "$K" --m "$M" --iterations "$ITERS" 2>&1 | grep -E '^Done\.' || true
done

bar "[2/5] Export the inspectable evidence (JSON + CSV) from Postgres"
uv run python -m ds_agent_loop.store export --out outputs/export 2>&1 | grep -Ei 'export' || true
note "-> outputs/export/  (cells, per-iteration records, compaction artifacts.json with full lineage)"

bar "[3/5] Analyse: token growth + paired regime differences"
uv run python -m ds_agent_loop.analysis --from outputs/export --out outputs/analysis 2>&1 | grep -vi alembic | tail -2 || true
note "-> outputs/analysis/  (outcomes.json, token_growth.png, paired_differences.png)"
note "-> notes/ablation_results.html  (open this in a browser to show the results)"

CELL_A="$MEMBER|recent_only|s$SEED|k$K|m$M"
CELL_B="$MEMBER|compacted_recent|s$SEED|k$K|m$M"

bar "[4/5] Audit: prove MEMORY was the only variable between the two cells"
uv run ds-agent-memory audit --cell-a "$CELL_A" --cell-b "$CELL_B" 2>&1 | grep -vi alembic | grep -E '^\[|dimension|comparison' || true

bar "[5/5] Audit the compaction operator's lineage (deterministic, 0 LLM calls)"
note "every artifact lists its trigger iteration, recorded cadence, and the exact source records it summarised."
uv run ds-agent-memory compaction "$CELL_B" 2>&1 | grep -vi alembic | grep -E '^\[|artifact' || true

bar "Done."
note "Re-run any step by hand — see notes/DEMO.md for the narrated walkthrough."
