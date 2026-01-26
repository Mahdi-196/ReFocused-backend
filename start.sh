#!/bin/sh
echo "--- Container starting up at $(date) ---"

echo "--- Starting Uvicorn server ---"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers