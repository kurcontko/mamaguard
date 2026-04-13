FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/mamaguard/

ENV AGENT_MODULE=mamaguard.app:a2a_app PORT=8001

EXPOSE ${PORT}

CMD exec uvicorn ${AGENT_MODULE} --host 0.0.0.0 --port ${PORT}
