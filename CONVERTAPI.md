# CV Text Extraction via ConvertAPI

## Why

The local extractor stack (pypdf/PyMuPDF, python-docx, pytesseract OCR, antiword/
libreoffice) depends on system binaries that aren't installed on Render, so it failed
on:
- scanned / image-based PDFs (need OCR),
- legacy `.doc` files,
- image CVs (JPG/PNG) — previously detected as "unknown" and skipped.

ConvertAPI (convertapi.com) is a managed service with proper OCR and broad format
coverage — no local binaries. It restores high extraction success (~99%).

## How it works

- The single dispatcher `workers/file_extractors.py::extract_text(filename, content)`
  now routes through ConvertAPI, with the local extractors as a safety net:
  - **mode "always"** (default): ConvertAPI first; on error/empty → local extractors.
  - **mode "fallback"**: local first; on miss/error → ConvertAPI (spends credit only on
    the hard cases).
  - **no secret configured**: behaves exactly like the old local-only pipeline (no regression).
- `integrations/convertapi_client.py` — `ConvertApiClient.to_text()` posts the file to
  `https://v2.convertapi.com/convert/{src}/to/txt` with OCR enabled for PDF/image sources,
  and returns the decoded text. Config is read from env first, then `system_settings`
  (cached ~5 min).
- Image formats (JPG/PNG/TIFF/WEBP) are now recognized by `detect_file_format` and routed
  to ConvertAPI OCR.

## Setup

Admin UI → **📄 סריקת CV (ConvertAPI)** (`/admin/convertapi`):
1. Paste your ConvertAPI **Secret** → **שמור הגדרות**. (Or set env `CONVERTAPI_SECRET`.)
2. **בדיקת חיבור** to validate the secret + see remaining credits.
3. Choose **mode**: "always" (max quality) or "fallback" (cost-saving) and OCR languages.
4. **עבד מחדש כשלונות עבר** — re-queues previously-failed CVs (flips `parse_status`
   `failed → pending`); the always-on `parse` stage re-extracts them via ConvertAPI.

## Cost

"always" mode spends one ConvertAPI credit per CV (and per reprocessed file). Use the
reprocess `limit` to control volume, and switch to "fallback" later to spend credits only
on files the local extractors can't read.

## Settings keys (system_settings)

`convertapi.secret`, `convertapi.enabled`, `convertapi.mode` (always|fallback),
`convertapi.ocr_languages` (default `en,he`). Env override: `CONVERTAPI_SECRET`.
