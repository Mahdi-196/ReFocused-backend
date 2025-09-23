#!/bin/sh
# This script will print debug info and then run the application

echo "--- Container starting up at $(date) ---"

echo "--- Printing environment variables for debugging ---"
printenv | sort
echo "--- End of environment variables ---"

echo "--- Attempting to start Uvicorn server ---"
exec uvicorn app.main_production:app --host 0.0.0.0 --port 8000