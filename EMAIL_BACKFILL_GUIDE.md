# Email Backfill System Guide

## Overview

The email intake system now supports two modes:

1. **Incremental Mode** (default) - Processes recent emails, ~100/run, conservative concurrency
2. **Backfill Mode** - Processes historical emails, ~500/run, high concurrency, 5-10x faster

## Starting a Backfill

### 1. Via API

```bash
curl -X POST http://localhost:8000/admin/email/start-backfill \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2021-05-01"}'
```

Response:
```json
{
  "status": "started",
  "start_date": "2021-05-01",
  "note": "Backfill will process ~500 emails per run. Check progress in status endpoint."
}
```

### 2. Via Frontend

Go to: **Pipeline Management → Email Intake Configuration**
- Click "Start Historical Backfill"
- Enter start date (e.g., "2021-05-01")
- System auto-detects and switches to backfill mode

## How Backfill Mode Works

### Mode Detection

The system automatically detects backfill mode by checking:
- `azure.backfill_start_date` is set (not null)
- `azure.last_seen_message_received_at` is null (backfill not yet started)

When both conditions are true:
- Processes **up to 500 emails per run** (vs 100 in normal mode)
- Uses **10 concurrent downloads** (vs 3)
- Uses **10 concurrent uploads** (vs 3)
- Expected throughput: **15,000-30,000 emails/hour**

### Processing Flow

1. **Every 2 minutes**, Celery task `ingest_emails_task` runs
2. Worker detects backfill mode from system settings
3. Fetches emails from `backfill_start_date` forward
4. Processes up to 500 emails per run
5. Updates `last_seen_message_received_at` with latest processed email
6. Continues next run from that timestamp

### Progress Tracking

Check progress via:
```bash
curl http://localhost:8000/admin/email/status
```

Response includes:
- `last_run_at` - When last ingest completed
- `emails_processed_total` - Cumulative count
- `cv_files_extracted_total` - Cumulative CVs
- `backfill_progress` - Current date being processed

## Performance Tuning

### Increase Concurrency (More Aggressive)

Edit `src/pandapower/workers/email_ingest.py`:

```python
MAX_CONCURRENT_DOWNLOADS_BACKFILL = 15  # was 10
MAX_CONCURRENT_UPLOADS_BACKFILL = 15    # was 10
```

⚠️ **Warning**: Higher concurrency may throttle Azure Graph API

### Increase Emails Per Run

Edit `src/pandapower/workers/email_ingest.py`:

```python
MAX_EMAILS_PER_RUN_BACKFILL = 1000  # was 500
```

⚠️ **Warning**: Larger batches may cause memory spikes or Celery task timeouts

## Monitoring Backfill Progress

### Real-Time Logs

```bash
# Terminal 1: Watch Celery worker logs
tail -f apps/backend/logs/celery.log | grep "backfill\|email ingest"
```

### Database Monitoring

```bash
# Check email intake log
SELECT 
  status,
  COUNT(*) as count,
  MAX(email_received_at) as latest_email,
  MAX(processing_completed_at) as last_processed
FROM email_intake_log
GROUP BY status
ORDER BY count DESC;

# Monitor system settings
SELECT setting_key, setting_value 
FROM system_settings 
WHERE setting_key LIKE 'azure.%';
```

### Expected Progression

For a 5-year backfill (2019-2024):

- **Hour 1-2**: Ramping up, discovering oldest emails
- **Hour 2-6**: Steady state, 15k-30k emails/hour
- **Day 1**: ~72,000-144,000 emails processed
- **Day 5**: Complete (assuming consistent rate)

Actual time depends on:
- Email volume per day
- Attachment sizes (larger = slower uploads)
- Azure API throttling
- Network bandwidth

## Troubleshooting

### Backfill Stuck (Not Processing)

1. Check if Celery Beat is running:
```bash
ps aux | grep "celery beat"
```

2. Check if Azure credentials are configured:
```bash
curl -X POST http://localhost:8000/admin/email/test-connection \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "YOUR_TENANT",
    "client_id": "YOUR_CLIENT",
    "client_secret": "YOUR_SECRET",
    "target_mailbox": "YOUR_EMAIL"
  }'
```

3. Check system settings:
```bash
SELECT * FROM system_settings 
WHERE setting_key LIKE 'azure.%'
ORDER BY setting_key;
```

### Slow Processing

If seeing <5,000 emails/hour:

1. Check Azure API throttling:
```bash
tail -f apps/backend/logs/celery.log | grep "429\|throttle"
```

2. Check if stuck on large attachment:
```bash
# Monitor in database
SELECT email_from, MAX(size) as max_attachment_size
FROM email_intake_log
WHERE status = 'processing'
GROUP BY email_from
HAVING MAX(size) > 10000000;  -- > 10 MB
```

3. Verify concurrency settings are applied:
```bash
grep "is_backfill" apps/backend/logs/celery.log | head -5
```

### Resume After Interruption

If backfill was interrupted:

1. Check last processed email:
```bash
SELECT * FROM system_settings 
WHERE setting_key = 'azure.last_seen_message_received_at';
```

2. Run manual trigger to continue:
```bash
curl -X POST http://localhost:8000/admin/email/run-now
```

System will automatically resume from `last_seen_message_received_at`.

## Switching Back to Incremental Mode

Once backfill is complete:

```bash
curl -X POST http://localhost:8000/admin/email/stop-backfill
```

Or manually clear the setting:

```bash
DELETE FROM system_settings 
WHERE setting_key = 'azure.backfill_start_date';
```

System will return to normal incremental mode (~100 emails/run).

## See Also

- [MEMORY.md](./memory/MEMORY.md) - Project history
- `src/pandapower/workers/email_ingest.py` - Implementation
- `src/pandapower/workers/tasks.py` - Celery task scheduling
- `src/pandapower/routers/admin/email_ingest.py` - API endpoints
