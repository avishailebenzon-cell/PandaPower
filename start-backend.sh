#!/bin/bash
set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$PROJECT_DIR/apps/backend"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting PandaPower Backend Services${NC}"
echo "Project: $PROJECT_DIR"
echo ""

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Installing tmux..."
    brew install tmux
fi

# Stop any existing session
tmux kill-session -t pandapower 2>/dev/null || true

# Create a new tmux session
tmux new-session -d -s pandapower -x 200 -y 50

# Window 1: Uvicorn Server
echo -e "${BLUE}📡 Starting Uvicorn Server...${NC}"
tmux new-window -t pandapower:0 -n "uvicorn"
tmux send-keys -t pandapower:uvicorn "cd $BACKEND_DIR && PYTHONPATH=src /opt/homebrew/bin/python3 -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000 --reload" C-m

# Wait for Uvicorn to start
sleep 3

# Window 2: Celery Worker + Beat (Scheduled Tasks)
echo -e "${BLUE}⚙️  Starting Celery Worker (with Beat scheduler)...${NC}"
tmux new-window -t pandapower:1 -n "celery"
tmux send-keys -t pandapower:celery "cd $BACKEND_DIR && PYTHONPATH=src /opt/homebrew/bin/python3 -m celery -A pandapower.workers.celery_app worker --beat --loglevel=info" C-m

# Wait for Celery to start
sleep 2

echo ""
echo -e "${GREEN}✅ Backend services started!${NC}"
echo ""
echo "Session: pandapower"
echo "Windows:"
echo "  - uvicorn (0): Uvicorn API server on http://localhost:8000"
echo "  - celery (1): Celery worker + beat scheduler"
echo ""
echo -e "${BLUE}Commands:${NC}"
echo "  tmux attach-session -t pandapower          # Attach to session"
echo "  tmux select-window -t pandapower:0         # Switch to Uvicorn window"
echo "  tmux select-window -t pandapower:1         # Switch to Celery window"
echo "  tmux kill-session -t pandapower            # Stop all services"
echo ""
echo -e "${GREEN}Backend is now running continuously in the background!${NC}"
echo "Press Ctrl+C here or use 'tmux kill-session -t pandapower' to stop."
echo ""

# Keep the script running so services stay active
tmux attach-session -t pandapower
