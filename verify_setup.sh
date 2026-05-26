#!/bin/bash
# PandaPower Phase 7 Setup Verification Script

set -e

echo "🔍 PandaPower Setup Verification"
echo "=================================="
echo ""

ERRORS=0
WARNINGS=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check backend .env
echo "📋 Checking Backend Configuration..."
if [ ! -f "apps/backend/.env" ]; then
    echo -e "${RED}✗ Missing: apps/backend/.env${NC}"
    ERRORS=$((ERRORS + 1))
else
    # Check required keys
    required_keys=("SUPABASE_URL" "SUPABASE_ANON_KEY" "AZURE_TENANT_ID" "AZURE_APP_CLIENT_ID" "AZURE_CLIENT_SECRET" "AZURE_TARGET_MAILBOX")
    for key in "${required_keys[@]}"; do
        if grep -q "^$key=" apps/backend/.env; then
            VALUE=$(grep "^$key=" apps/backend/.env | cut -d'=' -f2- | head -c 50)
            if [ -z "$VALUE" ] || [ "$VALUE" = "your-" ] || [ "$VALUE" = "placeholder" ]; then
                echo -e "${YELLOW}⚠ $key is not configured${NC}"
                WARNINGS=$((WARNINGS + 1))
            else
                echo -e "${GREEN}✓ $key configured${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ $key missing from .env${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    done
fi

echo ""
echo "📋 Checking Frontend Configuration..."
if [ ! -f "apps/frontend/.env.local" ]; then
    echo -e "${RED}✗ Missing: apps/frontend/.env.local${NC}"
    ERRORS=$((ERRORS + 1))
else
    required_keys=("VITE_SUPABASE_URL" "VITE_SUPABASE_ANON_KEY" "VITE_API_BASE")
    for key in "${required_keys[@]}"; do
        if grep -q "^$key=" apps/frontend/.env.local; then
            VALUE=$(grep "^$key=" apps/frontend/.env.local | cut -d'=' -f2- | head -c 50)
            if [ -z "$VALUE" ] || [ "$VALUE" = "placeholder" ]; then
                echo -e "${YELLOW}⚠ $key is not configured${NC}"
                WARNINGS=$((WARNINGS + 1))
            else
                echo -e "${GREEN}✓ $key configured${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ $key missing from .env.local${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    done
fi

echo ""
echo "📁 Checking Required Files..."
required_files=(
    "apps/backend/src/pandapower/main.py"
    "apps/backend/src/pandapower/workers/celery_app.py"
    "apps/backend/src/pandapower/workers/tasks.py"
    "apps/backend/src/pandapower/db/migrations.py"
    "apps/frontend/src/main.tsx"
    "apps/frontend/src/pages/admin/IntegrationsPage.tsx"
    "apps/frontend/src/pages/admin/EmailIntakePage.tsx"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ Missing: $file${NC}"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
echo "🔗 Checking Service Connectivity..."

# Check if backend is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend API is running${NC}"

    # Check /api/me endpoint
    if curl -s http://localhost:8000/api/me > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Authentication endpoint working${NC}"
    else
        echo -e "${YELLOW}⚠ /api/me endpoint not responding${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Backend API not running (not critical if not started yet)${NC}"
    echo "   Start with: cd apps/backend && PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --port 8000"
fi

# Check if frontend build exists
if [ -d "apps/frontend/dist" ]; then
    echo -e "${GREEN}✓ Frontend build exists${NC}"
else
    echo -e "${YELLOW}⚠ Frontend not built (will be built on npm run dev)${NC}"
fi

echo ""
echo "=================================="
echo "Summary:"
echo -e "${RED}Errors: $ERRORS${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"

if [ $ERRORS -eq 0 ]; then
    echo ""
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed! Ready to start.${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Terminal 1: cd apps/backend && PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --port 8000"
        echo "2. Terminal 2: cd apps/backend && PYTHONPATH=src uv run celery -A pandapower.workers.celery_app worker --beat --loglevel=info"
        echo "3. Terminal 3: cd apps/frontend && npm run dev"
        exit 0
    else
        echo -e "${YELLOW}⚠ Setup incomplete - configuration needs attention${NC}"
        echo ""
        echo "Please follow SETUP_CHECKLIST.md to complete configuration"
        exit 1
    fi
else
    echo ""
    echo -e "${RED}✗ Critical issues found - see above${NC}"
    exit 1
fi
