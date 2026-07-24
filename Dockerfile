FROM python:3.11-slim

WORKDIR /app

# Store commit hash for debugging
RUN echo "b5c3158-20260724T23" > /app/.deploy_version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway 注入 PORT 環境變數, 必須聽 $PORT 否則 Edge Proxy 連不上 (502/timeout)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
