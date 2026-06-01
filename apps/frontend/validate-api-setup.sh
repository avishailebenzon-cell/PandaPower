#!/bin/bash
# Validation script for frontend API configuration
# Checks that VITE_API_URL is correctly configured and files use API_BASE

set -e

echo "🔍 Validating PandaPower Frontend API Configuration..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERROR_COUNT=0
WARNING_COUNT=0

# Check 1: .env file exists
echo "1️⃣  Checking .env file..."
if [ -f .env ]; then
    echo -e "${GREEN}✅ .env file found${NC}"
else
    echo -e "${RED}❌ .env file not found${NC}"
    echo "   Run: cp .env.example .env"
    ((ERROR_COUNT++))
fi

# Check 2: VITE_API_URL is set
echo ""
echo "2️⃣  Checking VITE_API_URL variable..."
if grep -q "VITE_API_URL" .env 2>/dev/null; then
    API_URL=$(grep "VITE_API_URL" .env | cut -d'=' -f2)
    if [ -z "$API_URL" ]; then
        echo -e "${RED}❌ VITE_API_URL is empty${NC}"
        ((ERROR_COUNT++))
    else
        echo -e "${GREEN}✅ VITE_API_URL is set to: $API_URL${NC}"
    fi
else
    echo -e "${RED}❌ VITE_API_URL not found in .env${NC}"
    echo "   Add: VITE_API_URL=http://localhost:8000"
    ((ERROR_COUNT++))
fi

# Check 3: No old VITE_API_BASE variable
echo ""
echo "3️⃣  Checking for old variable names..."
if grep -q "VITE_API_BASE[^_]" .env 2>/dev/null; then
    echo -e "${RED}❌ Found VITE_API_BASE (old name, use VITE_API_URL instead)${NC}"
    ((ERROR_COUNT++))
elif grep -q "VITE_API_BASE_URL" .env 2>/dev/null; then
    echo -e "${RED}❌ Found VITE_API_BASE_URL (old name, use VITE_API_URL instead)${NC}"
    ((ERROR_COUNT++))
else
    echo -e "${GREEN}✅ No old variable names found${NC}"
fi

# Check 4: Check critical files use API_BASE
echo ""
echo "4️⃣  Checking if critical files use API_BASE..."

CRITICAL_FILES=(
    "src/api/pipedrive-data.ts"
    "src/api/matches.ts"
    "src/pages/admin/CarmitPage.tsx"
    "src/pages/admin/PandiReferralsPage.tsx"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        if grep -q "const API_BASE = import.meta.env.VITE_API_URL" "$file"; then
            echo -e "${GREEN}✅ $file has API_BASE declaration${NC}"
        else
            echo -e "${RED}❌ $file missing API_BASE declaration${NC}"
            ((ERROR_COUNT++))
        fi
    fi
done

# Check 5: Look for unprotected fetch calls
echo ""
echo "5️⃣  Scanning for unprotected fetch calls..."
UNPROTECTED=$(grep -r "fetch(['\"]\/admin\/\|fetch(['\"]\/api\/" src/ 2>/dev/null | grep -v "API_BASE" | wc -l)
if [ "$UNPROTECTED" -eq 0 ]; then
    echo -e "${GREEN}✅ No unprotected fetch calls found${NC}"
else
    echo -e "${YELLOW}⚠️  Found $UNPROTECTED unprotected fetch calls${NC}"
    echo "   These might cause 'Response is not JSON' errors"
    echo "   Run: grep -r \"fetch.*['\\\"]\/admin\/\" src/ | grep -v API_BASE"
    ((WARNING_COUNT++))
fi

# Check 6: Supabase credentials
echo ""
echo "6️⃣  Checking Supabase credentials..."
if grep -q "VITE_SUPABASE_URL" .env 2>/dev/null && grep -q "VITE_SUPABASE_ANON_KEY" .env 2>/dev/null; then
    echo -e "${GREEN}✅ Supabase credentials configured${NC}"
else
    echo -e "${YELLOW}⚠️  Supabase credentials not configured${NC}"
    echo "   Some features may not work without Supabase"
    ((WARNING_COUNT++))
fi

# Summary
echo ""
echo "================================"
echo "📊 Validation Summary"
echo "================================"
echo -e "Errors:   ${RED}$ERROR_COUNT${NC}"
echo -e "Warnings: ${YELLOW}$WARNING_COUNT${NC}"
echo ""

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✨ All critical checks passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Start the backend: cd apps/backend && uv run uvicorn pandapower.main:app --reload --port 8000"
    echo "2. Start the frontend: npm run dev"
    echo "3. Open http://localhost:5173 in your browser"
    echo "4. Check browser console for any errors"
else
    echo -e "${RED}❌ Some critical checks failed. Fix them above.${NC}"
    exit 1
fi

exit 0
