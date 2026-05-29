#!/bin/bash
# Simple background startup - runs both services as background processes

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$PROJECT_DIR/apps/backend"

echo "🚀 Starting PandaPower Backend Services (background mode)"
echo "Project: $PROJECT_DIR"
echo ""

# Create logs directory
mkdir -p "$BACKEND_DIR/logs"

# Start Uvicorn server in background
echo "📡 Starting Uvicorn Server (logs: logs/uvicorn.log)..."
cd "$BACKEND_DIR"
PYTHONPATH=src /opt/homebrew/bin/python3 -m uvicorn pandapower.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    > logs/uvicorn.log 2>&1 &
UVICORN_PID=$!
echo "   PID: $UVICORN_PID"

sleep 2

# Start Celery worker with beat in background
echo "⚙️  Starting Celery Worker + Beat (logs: logs/celery.log)..."
PYTHONPATH=src /opt/homebrew/bin/python3 -m celery -A pandapower.workers.celery_app \
    worker --beat --loglevel=info \
    > logs/celery.log 2>&1 &
CELERY_PID=$!
echo "   PID: $CELERY_PID"

echo ""
echo "✅ Services started!"
echo ""
echo "Monitor logs:"
echo "  tail -f $BACKEND_DIR/logs/uvicorn.log"
echo "  tail -f $BACKEND_DIR/logs/celery.log"
echo ""
echo "Stop services:"
echo "  kill $UVICORN_PID $CELERY_PID"
echo ""
echo "Or stop all backend processes:"
echo "  pkill -f 'uvicorn pandapower.main:app'"
echo "  pkill -f 'celery -A pandapower.workers.celery_app'"
