#!/bin/sh
# Railway passes the listen port in the PORT env var.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
