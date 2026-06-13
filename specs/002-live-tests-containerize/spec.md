# Feature Specification: Re-platform onto Google Vertex AI + Gemini (ADK), with Live Verification & Containerized Deployment

**Feature Branch**: `002-live-tests-containerize`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "Use the `notes/002-start-here.md` file to start the spec" — corrected with: "we need to use the Google framework leveraging Vertex AI and Gemini (their `google.genai` library) with ADK for the agent"

## ⚠ Blocking Dependency — Constitution Amendment Required

This feature introduces an agent framework (Google ADK), which is currently **prohibited**
by Constitution Principle I ("agent frameworks, or orchestration engines are prohibited")
and the Non-goals ("no multi-agent frameworks"). Per Governance, a conflicting change
requires the constitution to be **formally amended first** (a MAJOR version bump) — silent
deviation is not permitted. ADK is to be adopted **minimally**, constrained to the existing
two-call pattern (seed-generation + next-step) and the bounded-agency rules of Principles
II and III. **Planning and implementation MUST NOT begin until the constitution is amended.**

## Clarifications

### Session 2026-06-13

- Q: Which authentication mechanism reaches Vertex AI (locally and in the container)? → A: Application Default Credentials (ADC) — `gcloud` locally, mounted ADC file or workload identity in the container; no key committed or baked in.
- Q: Is the existing OpenAI-compatible backend removed or kept switchable after the re-platform? → A: Removed entirely — Gemini on Vertex AI via the Google SDK + minimal ADK is the sole LLM backend; no provider toggle.
- Q: What are the default Gemini model, region, and project for verification (overridable by the operator)? → A: Defaults `gemini-3.5-flash`, location `global`, project `research-se-gen-ai`; all overridable via environment.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Re-platform the loop onto Google's Gemini stack (Priority: P1)

The loop today reaches its model through an OpenAI-compatible client. The operator needs
the loop's single LLM backend replaced so that both LLM jobs — generating the seed
dataset/spec and proposing the next step — run against Google Gemini on Vertex AI, with the
agent built minimally on Google's ADK. The bounded design is preserved: the same two
structured contracts, the same model allowlist, and the same reject-bad-proposals behavior.

**Why this priority**: This is the foundational change the correction demands. Live
verification and containerization both depend on the loop actually talking to Gemini. It is
also where the safety boundary is most at risk (introducing an agent framework), so it must
be done first and correctly.

**Independent Test**: With the Google backend wired in but using a stubbed/offline model
client, run the existing behavioral checks and confirm the loop still issues exactly its two
structured requests, enforces the model allowlist, validates hyperparameters, and rejects
out-of-allowlist or malformed proposals — proving the re-platform preserves the bounded
contract without needing a live call.

**Acceptance Scenarios**:

1. **Given** the re-platformed loop, **When** it runs an iteration, **Then** the seed-generation and next-step interactions each use a developer-supplied structured contract and produce validated structured output — no free-form parsing and no additional LLM responsibilities.
2. **Given** the agent is built on ADK, **When** the loop executes, **Then** the agent is constrained to exactly the two sanctioned calls and takes no autonomous actions beyond them (no tool sprawl, no code execution).
3. **Given** a proposal naming a model outside the allowlist or carrying invalid hyperparameters, **When** the loop processes it, **Then** it is rejected and recorded and the prior best model is retained — identical to the pre-re-platform behavior.
4. **Given** the offline test suite, **When** it runs, **Then** it exercises the re-platformed loop with a stubbed model client and passes without making any network/LLM calls.

---

### User Story 2 - Verify the loop against live Gemini on Vertex AI (Priority: P2)

An operator supplies real Google Cloud credentials and a Gemini model and runs the loop
end-to-end once to confirm a genuine round-trip against Vertex AI produces the seed dataset,
drives the iterations, and writes a results file — proving the re-platformed loop works in
the wild, not just against a stub.

**Why this priority**: Until a real Vertex AI round-trip succeeds, the re-platform is
unproven. It delivers value on its own and is a prerequisite for trusting the container.

**Independent Test**: Provide valid Google Cloud credentials, project, location, and a Gemini
model, run the loop once, and confirm seed state files appear, the fixed iterations complete,
and a timestamped results file is written — all outside the offline test suite.

**Acceptance Scenarios**:

1. **Given** valid Google credentials, project, location, and a supported Gemini model, **When** the operator runs the loop, **Then** exactly one seed-generation round-trip produces the seed dataset and saved data specification, the configured iterations run, and a timestamped results file is written.
2. **Given** missing or invalid Google credentials, **When** the operator runs the loop, **Then** it fails fast at the first provider interaction with a clear, actionable message and no partial/silent success.
3. **Given** a Gemini model that cannot honor the structured contract, **When** the loop calls it, **Then** the failure is legible rather than a malformed result being silently accepted.
4. **Given** a completed run left valid saved state, **When** the operator re-runs against that state location, **Then** the seed step is skipped (no redundant seed round-trip) and the loop resumes from the checkpoint.
5. **Given** a completed live run, **When** the operator inspects the recorded history and best-run record, **Then** each iteration is captured with its metrics and rationale and the best run's primary metric is no worse than the baseline.

---

### User Story 3 - Run the loop as a portable container (Priority: P3)

An operator wants to run the loop on any machine without installing the toolchain locally.
They build a container image carrying the library and its consumer entrypoint, then run it by
supplying Google credentials and a Gemini model at launch, with run artifacts persisted
outside the container so results survive its exit.

**Why this priority**: Containerization mirrors the intended "publish library + deploy
consumer" model and makes the loop portable, but it depends on the re-platformed loop being
proven against live Vertex AI (Stories 1–2).

**Independent Test**: On a clean machine with only a container runtime, build the image, run
it with Google credentials and a Gemini model supplied at launch and a mounted artifact
location, and confirm a completed run leaves results in the mounted location after exit.

**Acceptance Scenarios**:

1. **Given** the project source, **When** the operator builds the container image, **Then** the build succeeds, installs the library and its consumer entrypoint, and the running container's default command launches the loop.
2. **Given** the built image, **When** the operator runs it with Google credentials and a Gemini model supplied at launch and an artifact location mounted, **Then** the loop runs against Vertex AI and the run's results persist in the mounted location after the container exits.
3. **Given** no credentials are supplied, **When** the container starts, **Then** it fails fast with a clear message and does not run partially.
4. **Given** the build context, **When** the image is built, **Then** no secrets/credentials and no local runtime artifacts (virtual environment, version-control metadata, existing run/state output) are baked into the image.

---

### Edge Cases

- What happens when the Google credentials lack permission for the target project/region, or the Gemini model is unavailable in that region? The failure must be clear and must not leave corrupt partial state.
- What happens when the provider is reachable but rejects the request (auth expired, quota, rate limit)? The failure must be legible and a clean re-run must remain possible.
- What happens when a Gemini model cannot satisfy the structured contract for one of the two calls? The system must surface this rather than silently accept malformed output.
- How does the agent layer behave if ADK attempts anything beyond the two sanctioned calls? Such behavior must be prevented or rejected, preserving bounded agency.
- How does the run behave when the build/runtime language version differs from the project's pinned version? The runtime base must be reconciled so a run does not fail on a version mismatch.
- What happens to a run interrupted partway (container killed mid-iteration)? Persisted state must remain inspectable and a subsequent run must not be corrupted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-000**: The constitution MUST be formally amended to permit the (minimal) use of an agent framework before planning or implementation proceeds; the amendment MUST preserve the structured-output (Principle II) and bounded-agency (Principle III) safety boundaries.
- **FR-001**: The loop's single LLM backend MUST be re-platformed so both sanctioned jobs (seed generation and next-step proposal) run against Google Gemini on Vertex AI via the Google generative-AI SDK. The prior OpenAI-compatible client MUST be removed entirely (no provider toggle, no dormant fallback); Gemini/Vertex is the sole backend.
- **FR-002**: The agent MUST be built minimally on Google ADK, constrained to exactly the two sanctioned structured calls; it MUST NOT introduce additional autonomous actions, tools, code execution, or extra LLM responsibilities.
- **FR-003**: Both LLM interactions MUST remain structured-output only against developer-supplied schemas, with results validated through the project's typed models; free-form parsing MUST NOT be introduced.
- **FR-004**: The model allowlist, hyperparameter validation, and rejection-of-invalid-proposals behavior MUST be preserved unchanged by the re-platform; rejected proposals MUST never be executed and the prior best model MUST be retained.
- **FR-005**: The offline automated test suite MUST exercise the re-platformed loop with a stubbed model client and MUST pass without making any network or LLM calls.
- **FR-006**: The loop MUST support running end-to-end against a real Vertex AI Gemini model. Valid ADC credentials are the only mandatory operator input; project, location, and Gemini model identifier default to documented values (`research-se-gen-ai`, `global`, `gemini-3.5-flash`) and are overridable via environment.
- **FR-007**: Google authentication MUST use Application Default Credentials (ADC); credentials and model/project/location selection MUST be supplied at run time through configuration/environment (ADC discovered via the standard Google mechanism) and MUST NOT be committed to the repository or embedded in any distributable artifact.
- **FR-008**: A live run MUST perform exactly one seed-generation round-trip when no valid prior state exists, producing the seed dataset and saved data specification.
- **FR-009**: When credentials are missing or invalid, the run MUST fail fast at the earliest provider interaction with a clear, actionable message and MUST NOT produce silent or partial success.
- **FR-010**: The system MUST provide a repeatable way to perform live verification manually that is kept separate from and excluded from the automated offline test suite.
- **FR-011**: A live run MUST be resumable: when valid saved state exists at the target location, the seed step MUST be skipped and the loop MUST continue from the existing checkpoint.
- **FR-012**: The system MUST record each iteration's outcome to the run history and persist the best run separately, accepting a new run only when the primary metric improves.
- **FR-013**: The system MUST be buildable into a portable container image that installs the library together with its consumer entrypoint and runs the loop as the container's default action.
- **FR-014**: The container build MUST exclude secrets/credentials and local runtime artifacts (virtual environment, version-control metadata, and existing state/output/run directories) from the image.
- **FR-015**: When run as a container, the loop's durable run artifacts MUST be persistable outside the container (e.g., via a mounted location) so results survive container exit and support resuming; Google credentials MUST be providable to the container at run time via mounted ADC (or workload identity) without being baked in.
- **FR-016**: The container's runtime language environment MUST be reconciled with the project's declared language version so that a build/run does not fail on a version mismatch.
- **FR-017**: Operator-facing documentation MUST describe how to configure Google credentials/project/location and a Gemini model, perform the live verification, and build/run the container, including artifact persistence and resume behavior.

### Key Entities *(include if data involved)*

- **Provider configuration**: Operator-supplied Google Cloud credentials, project, location/region, and Gemini model identifier needed to reach Vertex AI; supplied at run time, never persisted in the repo or image.
- **Agent**: The minimal ADK-based agent that performs exactly the two sanctioned structured calls and nothing more, preserving bounded agency.
- **Run artifacts**: The durable, human-readable outputs of a run — saved seed data and data specification, iteration history, best-run record, and the timestamped results file — inspectable and persistable across container runs.
- **Container image**: The portable, self-contained package carrying the library and its consumer entrypoint, parameterized only by run-time configuration (including Google credentials) and a mounted artifact location.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the re-platform, the offline test suite passes with zero network/LLM calls, and the loop still issues exactly two structured requests per iteration with the allowlist and rejection behavior intact — verifiable by inspecting recorded runs.
- **SC-002**: A bad proposal (out-of-allowlist model or invalid hyperparameters) is rejected and recorded and the prior best model retained, with no execution of the rejected proposal — behaviorally identical to before the re-platform.
- **SC-003**: An operator with valid Google credentials can complete one full live run against Vertex AI — from clean state through all configured iterations to a written results file — in a single command with no code changes.
- **SC-004**: A first live run with no prior state triggers exactly one seed-generation round-trip; a subsequent run against the same valid state triggers zero seed round-trips.
- **SC-005**: Every iteration of a completed live run is captured in the run history with its metrics and rationale, and the persisted best run's primary metric is no worse than the baseline.
- **SC-006**: A run started without credentials fails within the first provider interaction with a clear message and leaves no corrupt partial state that blocks a clean retry.
- **SC-007**: On a machine with only a container runtime and no project toolchain installed, an operator can build the image and complete a full live run, with results present in a mounted location after the container exits.
- **SC-008**: Inspection of the built image confirms it contains no secrets/credentials and none of the excluded local runtime artifacts.
- **SC-009**: An operator following only the provided documentation can perform both the live verification and the container build-and-run without needing to read the source.

## Assumptions

- **Constitution amendment is a prerequisite, not part of delivery scope**: FR-000 must be satisfied (constitution amended to permit minimal ADK use while preserving Principles II and III) before `/speckit-plan` proceeds. If the amendment is rejected, this feature must be revised to drop ADK.
- **Target backend is Google Gemini on Vertex AI** accessed via Google's generative-AI SDK (`google.genai`); the Gemini Developer API (API-key) path and other providers are out of scope. Authentication uses Application Default Credentials (ADC) plus project and location.
- **Documented, overridable defaults** are provided so a verification run needs only credentials: model `gemini-3.5-flash`, location `global`, project `research-se-gen-ai`. Each is overridable via environment; the project default is a convenience only and carries no committed secret.
- The existing implemented loop, offline test suite, and library/consumer structure from the prior phase are the starting point; the re-platform swaps the LLM backend and agent layer while preserving the loop's core behavior, schemas' intent, state files, and resume semantics.
- The two-schema, two-call design is retained; ADK is used only to host those two calls, not to add agency. Token usage still does not scale with dataset size (expansion stays local).
- Live LLM calls remain deliberately excluded from the automated offline test suite (kept hermetic and free); live verification is an operator-run, manual step.
- A single full live run (the fixed iteration count) is sufficient to validate the round-trip; load, concurrency, and long-running operation are out of scope.
- Persisting run artifacts via a mounted location is the chosen durability mechanism across container runs; an external orchestration/scheduling platform is out of scope.
- Publishing the library to an external artifact store and slimming the image to install from there is explicitly deferred and out of scope for this feature.
- Secrets/credentials are provided only at run time and never committed or baked into the image, consistent with the project's existing secret-handling practice.
