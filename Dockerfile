FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cache-bust: this RUN depends on the COPY above and changes every deploy,
# forcing Docker to re-evaluate (and re-COPY) the source layer on Railway.
RUN echo "railway-deploy-20260724T20" > /app/.deploy_nonce

EXPOSE 8000

# Railway 注入 PORT 環境變數, 必須聽 $PORT 否則 Edge Proxy 連不上 (502/timeout)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
