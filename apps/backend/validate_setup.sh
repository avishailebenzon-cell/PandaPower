#!/bin/bash
# PandaPower Setup Validation Script
# Verifies all components are in place and working

set -e

echo "🐼 PandaPower Setup Validation"
echo "=============================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check functions
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2 (missing: $1)"
        return 1
    fi
}

check_import() {
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

check_endpoint() {
    if curl -s http://localhost:8000$1 > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Endpoint $1"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} Endpoint $1 (backend may not be running)"
        return 1
    fi
}

# Validation sections
echo "📁 File Structure:"
check_file "src/pandapower/routers/admin/health.py" "Admin health router"
check_file "scripts/generate_test_data.py" "Test data generator"
check_file "MONITORING_GUIDE.md" "Monitoring guide"
check_file "START_HERE.md" "Getting started guide"
check_file "QUICK_REFERENCE.md" "Quick reference card"

echo ""
echo "🐍 Python Dependencies:"
check_import "fastapi" "FastAPI framework"
check_import "sqlalchemy" "SQLAlchemy ORM"
check_import "pydantic" "Pydantic validation"

echo ""
echo "📝 Configuration:"
check_file "src/pandapower/core/config.py" "Config module"
check_file "src/pandapower/core/supabase.py" "Supabase client"
check_file "src/pandapower/main.py" "Main application"

echo ""
echo "🌐 Backend Status:"
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Backend is running"

    echo ""
    echo "📊 Health Check Endpoints:"
    check_endpoint "/admin/health"
    check_endpoint "/admin/pipeline-status"
    check_endpoint "/admin/agents/status"

    echo ""
    echo "🎯 Sample Match Endpoint:"
    check_endpoint "/admin/matches/test/history"
else
    echo -e "${YELLOW}⚠${NC} Backend is not running (start with: python3 -m uvicorn src.pandapower.main:app --reload)"
fi

echo ""
echo "✅ Validation Complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Start backend (if not running):"
echo "   python3 -m uvicorn src.pandapower.main:app --reload"
echo ""
echo "2. Generate test data:"
echo "   python3 scripts/generate_test_data.py --verbose"
echo ""
echo "3. Check quick reference:"
echo "   cat QUICK_REFERENCE.md"
echo ""
echo "4. Read full guide:"
echo "   cat MONITORING_GUIDE.md"
echo ""
