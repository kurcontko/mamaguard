FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY requirements.lock.txt .
RUN uv pip install --system --no-cache -r requirements.lock.txt

COPY . /app/mamaguard/

ENV AGENT_MODULE=mamaguard.app:a2a_app PORT=8001

EXPOSE ${PORT}

CMD exec uvicorn ${AGENT_MODULE} --host 0.0.0.0 --port ${PORT}
