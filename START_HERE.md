# Start Here

Resuming work on the **LLM Autonomous Data Scientist (Toy) Loop** (branch `001-autods-loop`).

## Read first
- Constitution: `.specify/memory/constitution.md` (v1.2.0 — uv, notes/ progress, no AI co-author in commits, Pydantic models + centralized settings)
- Spec: `specs/001-autods-loop/spec.md`
- Plan: `specs/001-autods-loop/plan.md`
- Tasks: `specs/001-autods-loop/tasks.md` ← implementation checklist

## Status
Spec / plan / tasks complete and analyzed. Not yet implemented (no source code written).

## Next
Run `/speckit-implement` to execute tasks, starting with Phase 1 (Setup).

## Open analysis items (optional, pre-implementation)
- C1: decide where the `pydantic-settings` Settings object lives (avoid an unsanctioned `config.py` vs the fixed flat module list).
- G1: add an explicit action-dispatch task (apply expand/tune/switch/keep/stop).
- G2: add a corrupt/unreadable state-file error task.
