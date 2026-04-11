FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the mamaguard package into /app/mamaguard/ so that
# `import mamaguard.app` resolves correctly.
COPY . /app/mamaguard/

ENV AGENT_MODULE=mamaguard.app:a2a_app
ENV PORT=8001

EXPOSE ${PORT}

CMD uvicorn ${AGENT_MODULE} --host 0.0.0.0 --port ${PORT}
