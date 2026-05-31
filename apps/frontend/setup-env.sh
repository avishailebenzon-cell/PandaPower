#!/bin/bash
# Setup script for frontend environment variables

echo "🔧 Setting up PandaPower Frontend Environment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created. Please update with your values."
else
    echo "✅ .env file already exists"
fi

# Check if required variables are set
if ! grep -q "VITE_API_URL" .env; then
    echo "⚠️  Warning: VITE_API_URL not found in .env"
    echo "   This variable is required for the API proxy to work."
    echo "   Please add: VITE_API_URL=http://localhost:8000"
fi

if ! grep -q "VITE_SUPABASE_URL" .env; then
    echo "⚠️  Warning: VITE_SUPABASE_URL not configured"
fi

if ! grep -q "VITE_SUPABASE_ANON_KEY" .env; then
    echo "⚠️  Warning: VITE_SUPABASE_ANON_KEY not configured"
fi

echo "✨ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env with your Supabase credentials"
echo "2. Ensure VITE_API_URL is set to your backend (default: http://localhost:8000)"
echo "3. Run: npm install && npm run dev"
