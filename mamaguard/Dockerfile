FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered stdout/stderr for Cloud Run logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the mamaguard package into /app/mamaguard/ so that
# `import mamaguard.app` resolves correctly.
COPY . /app/mamaguard/

ENV AGENT_MODULE=mamaguard.app:a2a_app
# Default port; Cloud Run overrides PORT at runtime.
ENV PORT=8001

EXPOSE ${PORT}

HEALTHCHECK --interval=10s --timeout=5s --retries=6 --start-period=15s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/.well-known/agent-card.json')" || exit 1

# Use exec so uvicorn receives SIGTERM directly from Cloud Run for graceful shutdown.
CMD exec uvicorn ${AGENT_MODULE} --host 0.0.0.0 --port ${PORT}
