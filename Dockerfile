FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache-bust: force re-COPY of all source on every deploy (Railway build cache
# was reusing a stale data_service.py layer). Value bumped per deploy.
ENV RAILWAY_REBUILD_NONCE=20260715-03

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
