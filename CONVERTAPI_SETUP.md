# ConvertAPI Setup

## Status
✅ ConvertAPI secret configured in system_settings database
✅ ConvertAPI mode: "always" (try OCR first, fallback to local)
❌ **MISSING**: CONVERTAPI_SECRET environment variable in Render

## Issue
When running on Render, the app reads CONVERTAPI_SECRET from environment variables, but it's not set there. The local `.env` file won't be deployed (it's in `.gitignore` for security).

## Solution
Add CONVERTAPI_SECRET to Render environment variables:

1. Go to: https://dashboard.render.com/
2. Select **pandapower-backend** service
3. Click **Environment**
4. Add variable:
   - **Key**: `CONVERTAPI_SECRET`
   - **Value**: `0ZMHmec1aGLLkRfRlr4M3bbFhO6U7Mhd`
5. Click **Save Changes**
6. Service will auto-deploy with new environment

## What This Does
- Enables OCR text extraction via ConvertAPI for images, scanned PDFs, legacy .doc files
- CVs will be processed through ConvertAPI first (mode="always")
- Fallback to local extractors (pypdf, python-docx, etc.) if ConvertAPI fails

## Current Flow
```
CV File → Extract Text:
  ├─ Mode "always" (enabled):
  │  ├─ Try ConvertAPI OCR first
  │  └─ If fails → Local extractors (pypdf, python-docx, etc.)
  └─ Results in raw_text field in cv_files table
    
CV with raw_text → Parse with Claude → Extract fields
```

## Testing (Local)
```bash
cd apps/backend
export PYTHONPATH="/Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend/src"
python3 -c "
import asyncio
from pandapower.integrations.convertapi_client import get_convertapi_config

async def test():
    cfg = await get_convertapi_config()
    print(f'Enabled: {cfg.get(\"enabled\")}')
    print(f'Secret: {\"YES\" if cfg.get(\"secret\") else \"NO\"}')

asyncio.run(test())
"
```

## Files Involved
- `apps/backend/.env` - Local development (not deployed)
- `apps/backend/src/pandapower/workers/file_extractors.py` - Extract logic
- `apps/backend/src/pandapower/integrations/convertapi_client.py` - ConvertAPI client
- `apps/backend/src/pandapower/workers/cv_parse.py` - CV parsing task

## References
- ConvertAPI docs: https://convertapi.com/doc
- API endpoint: https://v2.convertapi.com/convert/...
- Dashboard: https://convertapi.com/a/dashboard/account

