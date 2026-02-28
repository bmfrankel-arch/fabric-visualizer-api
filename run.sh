#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting Fabric Visualizer ==="
echo ""

# Build frontend if needed
DIST="$DIR/frontend/dist"
if [ ! -d "$DIST" ] || [ "$1" = "--build" ]; then
    echo "Building frontend..."
    cd "$DIR/frontend"
    npx vite build
    echo ""
fi

# Start backend (serves both API + frontend)
echo "Starting server on http://localhost:8000 ..."
cd "$DIR/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
PID=$!

echo ""
echo "  App:      http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $PID 2>/dev/null; exit" INT TERM
wait
