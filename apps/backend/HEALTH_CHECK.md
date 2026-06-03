# 🏥 System Health Check

## Overview

The Health Check system monitors all critical integrations and leverages the unified **Alert Service** for notifications. This ensures:
- ✅ No duplicate alerting logic
- ✅ Consistent throttling and user acknowledgement
- ✅ Both email (Resend) and Telegram notifications
- ✅ Full management via `/admin/alerts` UI

## What Gets Monitored

✅ **ConvertAPI** - Text extraction & OCR service
✅ **Pipedrive** - CRM integration  
✅ **Azure Email** - Email inbox scanning
✅ **Supabase** - Database connection
✅ **Anthropic API** - Claude API connection

## How It Works

1. **Every 10 minutes** → `health_check_task()` runs
2. **Tests each integration** → checks connectivity, credits, token validity
3. **Issues found?** → calls `alert_admin()` from Alert Service
4. **Alert Service handles:**
   - Sending email (Resend) + Telegram notifications
   - 30-min cooldown per component (no spam)
   - User snooze/acknowledge via `/admin/alerts` UI
   - Respects global alert configuration

## Integration with Alert Service

See: `/admin/alerts` for:
- ✅ View all alerts
- ✅ Snooze globally (all alerts paused)
- ✅ Acknowledge per component (mute "health-convertapi", etc.)
- ✅ Enable/disable alerts
- ✅ Configure admin email

## Check Details

### ConvertAPI
- Secret validity
- Credit balance (warns if < 100)

### Pipedrive
- API token configured
- Validation: token length > 10 chars

### Azure Email
- All credentials present (tenant, client, secret, mailbox)
- Mailbox connectivity test

### Supabase
- Database connection test

### Anthropic
- API key configured
- Validation: key length > 20 chars

## Alert Keys (for `/admin/alerts` acknowledgement)

- `health-convertapi` - ConvertAPI issues
- `health-pipedrive` - Pipedrive issues
- `health-azure_email` - Azure email issues
- `health-supabase` - Database issues
- `health-anthropic` - Claude API issues

## Configuration

Ensure these are set in `.env`:

```bash
RESEND_API_KEY=re_xxx...      # For email delivery
ADMIN_EMAIL=you@example.com   # Alert recipient
```

## Disabling / Throttling

Via `/admin/alerts` UI:

```bash
# Snooze all alerts for 30 min
POST /admin/alerts/snooze { "minutes": 30 }

# Acknowledge (mute) health-convertapi for 2 hours
POST /admin/alerts/acknowledge { "key": "health-convertapi", "minutes": 120 }

# Disable all alerts
POST /admin/alerts/config { "enabled": false }
```

## Implementation

See: `workers/health_check.py`

- `HealthCheckWorker`: Runs tests on all integrations
- `HealthCheckWorker._send_alert()`: Calls `alert_admin()` from Alert Service
- Each issue becomes a separate alert for granular control

## No Duplicate Code

This health check **integrates with** the existing Alert Service:
- Bottleneck alerts → pipeline health
- Health check alerts → integration health
- Both use same throttling, UI, and configuration

## Troubleshooting

**Q: Not receiving alerts?**
- Check `/admin/alerts` → ensure enabled
- Verify global snooze not active
- Check if component is acknowledged
- Verify `RESEND_API_KEY` and `ADMIN_EMAIL` in `.env`

**Q: Too many alerts?**
- Use `/admin/alerts/snooze` to pause temporarily
- Acknowledge specific components you don't want to hear from
- Cooldown is 30 minutes per component

**Q: Want to test it?**
- Manually break an integration (e.g., paste fake Pipedrive token)
- Next health check will alert
- Use `/admin/alerts/acknowledge` to mute it
