# Frontend Setup Guide

## Quick Setup (Recommended)

```bash
cd apps/frontend
bash setup-env.sh
npm install
npm run dev
```

The setup script will:
1. Create `.env` from `.env.example`
2. Validate required environment variables
3. Warn you if critical variables are missing

## Manual Setup

If you prefer manual setup:

### 1. Create `.env` file

```bash
cd apps/frontend
cp ../.env.example .env
```

### 2. Configure Environment Variables

Edit `apps/frontend/.env` and set:

```env
# CRITICAL: Must be VITE_API_URL (not VITE_API_BASE or VITE_API_BASE_URL)
VITE_API_URL=http://localhost:8000

# Supabase credentials (from your Supabase project)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### 3. Install Dependencies

```bash
npm install
```

### 4. Start Development Server

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

## Environment Variable Reference

### VITE_API_URL (Required)
- **Purpose:** Backend API endpoint for data fetching
- **Default:** `http://localhost:8000` (local development)
- **Production:** Your deployed backend URL
- **⚠️ Common Error:** Using `VITE_API_BASE` or `VITE_API_BASE_URL` instead
  - This will cause "Response is not JSON (received text/html)" errors
  - The frontend's Vite proxy looks specifically for `VITE_API_URL`

### VITE_SUPABASE_URL (Required)
- **Purpose:** Supabase project URL for database/auth
- **Example:** `https://xknzpurparakylocrnld.supabase.co`
- **Get it from:** Supabase project settings

### VITE_SUPABASE_ANON_KEY (Required)
- **Purpose:** Public API key for Supabase
- **Get it from:** Supabase project settings → API

## Troubleshooting

### "Failed to fetch employees: Response is not JSON"

**Problem:** API requests are getting HTML instead of JSON

**Causes:**
1. `VITE_API_URL` is not set or is wrong
2. `VITE_API_URL` is set to `VITE_API_BASE` (wrong variable name)
3. Backend is not running on the configured port

**Fix:**
1. Verify `apps/frontend/.env` has correct `VITE_API_URL`
2. Restart dev server: `npm run dev`
3. Hard refresh browser: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
4. Verify backend is running: `curl http://localhost:8000/health`

### "Cannot find SUPABASE variables"

**Problem:** Supabase credentials are not configured

**Fix:**
1. Get credentials from your Supabase project
2. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `.env`
3. Restart dev server

### Dev Server Won't Start

**Problem:** `npm run dev` fails

**Fix:**
1. Delete `node_modules` and `.vite`: `rm -rf node_modules .vite`
2. Clear npm cache: `npm cache clean --force`
3. Reinstall: `npm install`
4. Start again: `npm run dev`

## Development Workflow

### Running Tests
```bash
npm test
```

### Type Checking
```bash
npx tsc --noEmit
```

### Building for Production
```bash
npm run build
```

### Preview Production Build
```bash
npm run preview
```

## File Structure

```
apps/frontend/
├── src/
│   ├── api/              # API client functions
│   ├── components/       # Reusable React components
│   ├── hooks/            # Custom React hooks
│   ├── pages/            # Page components
│   ├── lib/              # Utilities and helpers
│   ├── index.css         # Global styles
│   └── main.tsx          # Entry point
├── .env                  # Environment variables (local, git-ignored)
├── .env.example          # Environment variable template
├── package.json          # Dependencies
├── tsconfig.json         # TypeScript config
├── vite.config.ts        # Vite build config
├── tailwind.config.js    # Tailwind CSS config
└── setup-env.sh          # Setup automation script
```

## Key Technologies

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool & dev server
- **Tailwind CSS** - Styling
- **React Router** - Client-side routing
- **TanStack Query** - Data fetching & caching
- **Supabase** - Backend-as-a-Service

## Best Practices

1. **Always commit `.env.example`** - Never commit actual `.env` files
2. **Use environment variables** - Don't hardcode API URLs or keys
3. **Type everything** - Leverage TypeScript for safety
4. **Test components** - Write tests for complex components
5. **Use React hooks** - Build custom hooks for shared logic

## Validation

Before starting development, validate your setup:

```bash
cd apps/frontend
bash validate-api-setup.sh
```

This script checks:
- ✅ .env file exists
- ✅ VITE_API_URL is configured
- ✅ No old variable names (VITE_API_BASE, VITE_API_BASE_URL)
- ✅ All critical files use API_BASE
- ✅ No unprotected fetch calls
- ✅ Supabase credentials configured

## Support

If you encounter issues:
1. Run: `bash validate-api-setup.sh` to identify configuration problems
2. Check [FRONTEND_API_VALIDATION.md](./FRONTEND_API_VALIDATION.md) for detailed API troubleshooting
3. Check this troubleshooting guide
4. Check `README.md` troubleshooting section
5. Check recent commits for changes to env variable names
6. Ask in team chat with error message and what you've tried
