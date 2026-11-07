FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 postgresql-client fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend /app/backend
COPY scripts /app/scripts
COPY data /app/data
COPY alembic.ini /app/alembic.ini
ENV PYTHONUNBUFFERED=1
RUN useradd -m pharma && mkdir -p /app/ml/models && chown -R pharma:pharma /app
USER pharma
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
