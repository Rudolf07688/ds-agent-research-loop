"""Manual live verification against real Vertex AI / Gemini (US2).

This is intentionally NOT a pytest test — it makes real LLM calls and is excluded from the
hermetic offline suite (FR-005, FR-010). Run it by hand after authenticating with ADC:

    gcloud auth application-default login
    uv run python entrypoint/smoke_live.py

It performs one end-to-end run and asserts the success criteria:
  SC-001/003  seed files + iterations + results file written; history has metrics+rationale
  SC-004      first run does exactly one seed call; a second run resumes (zero seed calls)
  SC-005      best run is recorded and no worse than the baseline

Resume (SC-004 / FR-011) is exercised by running against a PERSISTENT state directory:
re-running this script reuses the saved seed/spec instead of re-seeding. Delete the
``--fresh`` directory (printed below) to force a clean first run.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from ds_agent_loop import Settings, run_loop
from ds_agent_loop.main import SUMMARY_FILE

REPO_ROOT = Path(__file__).resolve().parent.parent
SMOKE_STATE = REPO_ROOT / "entrypoint" / "runs" / "smoke-state"


def _check(label: str, ok: bool) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return ok


def main() -> int:
    fresh = "--fresh" in sys.argv
    if fresh and SMOKE_STATE.exists():
        for p in sorted(SMOKE_STATE.glob("*")):
            p.unlink()
        print(f"Cleared {SMOKE_STATE} for a fresh first run.")

    seed_existed = (SMOKE_STATE / "seed_rows.json").exists() and (
        SMOKE_STATE / "data_spec.json"
    ).exists()
    mode = "RESUME (expect zero seed calls)" if seed_existed else "FIRST RUN (expect one seed call)"
    print(f"Live smoke — mode: {mode}")
    print(f"State dir : {SMOKE_STATE}")

    settings = Settings(n_iterations=5)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outputs_dir = (REPO_ROOT / "entrypoint" / "runs" / f"smoke_{timestamp}").resolve()
    SMOKE_STATE.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Backend   : project={settings.google_cloud_project} "
        f"location={settings.google_cloud_location} model={settings.gemini_model}"
    )
    asyncio.run(run_loop(settings, state_dir=SMOKE_STATE, outputs_dir=outputs_dir))

    print("\nAssertions:")
    ok = True
    ok &= _check("seed_rows.json present", (SMOKE_STATE / "seed_rows.json").exists())
    ok &= _check("data_spec.json present", (SMOKE_STATE / "data_spec.json").exists())
    results_path = outputs_dir / SUMMARY_FILE
    ok &= _check(f"results written ({SUMMARY_FILE})", results_path.exists())

    history_path = SMOKE_STATE / "history.json"
    best_path = SMOKE_STATE / "best_run.json"
    ok &= _check("history.json present", history_path.exists())
    ok &= _check("best_run.json present", best_path.exists())
    if history_path.exists():
        hist = json.loads(history_path.read_text())
        ok &= _check(
            "every iteration has metrics + rationale",
            bool(hist) and all("metrics" in r and r.get("rationale") for r in hist),
        )
    if best_path.exists() and history_path.exists():
        best = json.loads(best_path.read_text())
        baseline = json.loads(history_path.read_text())[0]
        ok &= _check(
            "best RMSE <= baseline RMSE (SC-005)",
            best["metrics"]["rmse"] <= baseline["metrics"]["rmse"],
        )

    print(
        "\nNOTE: re-run this script (without --fresh) to verify resume skips seeding (SC-004),\n"
        "and run once with credentials unset to verify fail-fast (SC-006)."
    )
    print(f"\nLIVE SMOKE: {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
