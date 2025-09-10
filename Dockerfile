FROM python:3.13-slim AS builder

WORKDIR /app   

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN python -m venv venv && venv/bin/pip install --upgrade pip && \
        venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
WORKDIR /app

COPY --from=builder /app/venv/ /app/venv/

COPY README.md src/app.py .

ENV PATH="/app/venv/bin:$PATH"

CMD ["uvicorn", "app:app", "--host",  "0.0.0.0", "--port",  "8000", "--timeout", "600"]
