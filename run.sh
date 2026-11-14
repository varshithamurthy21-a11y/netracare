#!/usr/bin/env bash
# One command to start NetraCare: API on :8000, app on :8501
set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
python -m uvicorn backend.main:app --port 8000 &
API=$!
trap "kill $API" EXIT
sleep 2
python -m streamlit run frontend/app.py --server.port 8501
