# Multi-stage build: install deps (cached) then the package, run the entrypoint consumer.
# Mirrors the "publish library + deploy consumer" model. Secrets/credentials are NEVER
# baked in — pass ADC + config at run time (see README / quickstart).

# ---- Stage 1: resolve and install dependencies (cached on lockfile) -------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS deps

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy only the dependency manifests first so this layer caches across source changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- Stage 2: install the project and ship the consumer entrypoint --------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    GOOGLE_GENAI_USE_VERTEXAI=TRUE

WORKDIR /app

# Bring in the pre-built virtualenv from the deps stage.
COPY --from=deps /app/.venv /app/.venv

# Copy the library + consumer and install the package into the venv.
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY entrypoint/ ./entrypoint/
RUN uv sync --frozen --no-dev

# Bake non-secret defaults from a local `.env` if one is present in the build context.
# pydantic-settings loads this `.env` at runtime, but REAL environment variables (e.g. the
# README's `docker run -e ...` flags) take precedence over it — so this only fills in
# defaults for an almost-zero-setup run and never overrides explicit overrides. The glob
# also matches `.env.example` (always present), so this COPY never fails when `.env` is
# absent. Credentials are excluded by .dockerignore and never end up here.
COPY .env* ./

# Runtime artifact directories (mount these as volumes to persist across container exit).
RUN mkdir -p state outputs entrypoint/runs

# Default action: run the loop via the consumer entrypoint.
ENTRYPOINT ["uv", "run", "python", "entrypoint/run.py"]
