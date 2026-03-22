FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

RUN groupadd -r app && useradd -r -d /app -g app -N app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

COPY --chown=app:app . .

RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

USER app

# Override CMD in your deployment to point at your config module, e.g.:
# CMD ["python", "examples/redis_worker/config.py"]
