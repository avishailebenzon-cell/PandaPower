# מדריך קליטת הדוא"ל - Email Intake System

## 📋 סקירה כללית

מערכת קליטת הדוא"ל של PandaPower היא **מערכת אוטונומית לסריקה רציפה של דוא"לים** מ-Outlook של משרד:

- ✅ **סריקה אוטומטית כל שניים דקות** - העיבוד מתרחש ברקע
- ✅ **ניהול וב"ף היסטורי** - עבור מיליוני מיילים מעבר
- ✅ **ניתור התקדמות בזמן אמת** - ראו התקדמות ה-backfill
- ✅ **טיפול בכשלים אוטומטי** - עם retry mechanism

## 🔧 הגדרה ראשונית

### 1. קונפיגורציה של Azure

בדף **Admin → Email Intake** → **Test Connection**:

```
Tenant ID:      {your-tenant-id}
Client ID:      {your-client-id}
Client Secret:  {your-client-secret}
Target Mailbox: recruitment@company.co.il
```

אחרי בדיקה מוצלחת, לחץ **Save Configuration**.

### 2. התחלת Backfill (סריקת היסטוריה)

```
Admin → Email Intake → Start Backfill

Start Date: 2023-01-01  (או כל תאריך אחר)
```

זה יתחיל לסרוק את כל המיילים מ-2023-01-01 עד היום.

## 🚀 איך זה עובד

### מחזור סריקה

```
כל 2 דקות:
  1. Azure API: קבל עד 20 מיילים
  2. בדוק קבצים קיימים (שכפולות)
  3. הוסף לאחסון ל-Supabase
  4. עדכן את last_seen timestamp
  5. המשך עם batch הבא
```

### תהליך עיבוד קבצים

```
עבור כל attachment:
  1. בדוק גודל (דלג אם > 50MB)
  2. הורד מ-Azure עם retry (עד 3 פעמים)
  3. חשב SHA-256 hash (למניעת שכפולות)
  4. בדוק קיום בבסיס הנתונים
  5. העלה ל-Supabase Storage עם path ייחודי
  6. צור record ב-cv_files table עם versioning
```

## 📊 מעקב התקדמות

### Status Endpoint

```bash
curl -X GET "http://localhost:8000/admin/email/status"
```

תשובה:

```json
{
  "last_run_at": "2026-05-25T14:30:00Z",
  "last_status": "active",
  "emails_processed_today": 45,
  "emails_processed_total": 2340,
  "cv_files_extracted_today": 12,
  "cv_files_extracted_total": 340
}
```

### Backfill Progress

```bash
curl -X GET "http://localhost:8000/admin/email/backfill-progress"
```

תשובה:

```json
{
  "backfill_enabled": true,
  "backfill_start_date": "2023-01-01T00:00:00",
  "last_processed_at": "2026-05-20T14:30:00Z",
  "progress_percent": 68,
  "days_remaining": 150
}
```

## 🎯 דוגמאות שימוש

### התחלת Backfill מ-2022

```bash
curl -X POST "http://localhost:8000/admin/email/start-backfill" \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2022-01-01"}'
```

### ריצה ידנית כעת

```bash
curl -X POST "http://localhost:8000/admin/email/run-now"
```

### ביטול Backfill

```bash
curl -X POST "http://localhost:8000/admin/email/cancel-backfill"
```

### קבלת לוגים אחרונים

```bash
curl -X GET "http://localhost:8000/admin/email/logs?limit=50&status=success"
```

## 🔍 בדיקת טעויות

### בדיקת Logs

בדפי **Admin → Email Intake → History Table** ראו את ה-status:

- ✅ **בהצלחה** - קורות חיים חולצו בהצלחה
- ⚠️ **דלג** - אין קורות חיים בדוא"ל
- ❌ **כשל** - שגיאה בעיבוד

לחץ על השורה כדי לראות פרטי השגיאה.

### בדוקה ידנית

```python
# בתוך Python shell
import asyncio
from pandapower.workers.email_ingest import EmailIngestWorker
from pandapower.integrations.azure import AzureGraphClient

# Setup clients...
worker = EmailIngestWorker(supabase, azure, storage)
result = await worker.ingest_recent_emails(batch_size=20)
print(result)
```

## ⚙️ הגדרות יתקדמות

### Tuning ביצועים

בתוך `email_ingest.py`:

```python
MAX_CONCURRENT_DOWNLOADS = 3    # הורדות בו-זמניות (Azure API limits)
MAX_CONCURRENT_UPLOADS = 3      # העלאות בו-זמניות (Supabase limits)
MAX_ATTACHMENT_SIZE_MB = 50     # דלג על קבצים גדולים מ-50MB
```

### גודל Batch

ה-default הוא 20 מיילים per run.
ב-backfill של 1M מיילים:

- 20 דקות/לולאה × 3 רצות = ~1 שעה ל-~3,600 מיילים
- **~270 שעות (~11 ימים) ל-1M מיילים**

כדי להאיץ, הגדל `batch_size`:

```python
# בadmin panel
await worker.ingest_recent_emails(batch_size=50)  # 50 instead of 20
```

## 🛡️ טיפול בשגיאות

### שגיאות נפוצות

| שגיאה | סיבה | פתרון |
|-------|------|--------|
| `Azure settings not configured` | לא הגדרת התאמות | עבור ל-Configure ב-UI |
| `401 Unauthorized` | Azure credentials שגויות | בדוק app registration |
| `Connection timeout` | Azure API לא משיב | בדוק חיבור אינטרנט |
| `Duplicate key value` | CV כפול | מדלג אוטומטית בפעם הבאה |

### Retry Logic

כשלים באחסון = retry עד 3 פעמים עם exponential backoff:
- Attempt 1: מיידי
- Attempt 2: חכה 1 שנייה
- Attempt 3: חכה 2 שניות

## 🔄 Workflow דוגמה מלא

```
יום 1:
  ✓ Admin: Configure Azure credentials
  ✓ Admin: Start backfill from 2023-01-01
  
יום 2-14:
  ✓ כל 2 דקות: email ingest task רץ אוטומטית
  ✓ Monitor: בדוק progress בـ status endpoint
  ✓ Optional: טוויק batch_size אם צריך להאיץ
  
יום 14:
  ✓ Backfill הושלם (כל המיילים מ-2023 מעובדים)
  ✓ Admin: Cancel backfill (חזור לnormal mode)
  
ממשיך:
  ✓ כל שעה: scan מיילים חדשים
  ✓ אוטומטית: טוענים קורות חיים לבדיקה עבור טור שמיות
```

## 📈 ניטור בפרודקשן

אם פועל ב-production עם Redis:

```bash
# בדוק queue length
redis-cli LLEN celery

# בדוק task history
redis-cli HGETALL celery-task-meta-{task_id}

# Monitor active tasks
celery -A pandapower.workers.celery_app inspect active
```

## 🎓 FAQ

**Q: איך יודע אם backfill עובד?**
A: בדוק את `/admin/email/backfill-progress` כל דקה. ה-`progress_percent` צריך לגדול.

**Q: קבצים גדולים מדי דלג?**
A: כן, ברירת מחדל היא דלג על קבצים > 50MB. שנה `MAX_ATTACHMENT_SIZE_MB` אם צריך.

**Q: כמה מהר זה משתפר כשאוסיף עוד workers?**
A: במצב production עם Redis, כל worker יכול לעבד טוג"ח שונה בו-זמנית. תוספת 4 workers = ~4x faster.

**Q: מה קורה אם יש כשל?**
A: Task מנסה שוב עם exponential backoff עד 3 פעמים, אחרי זה מדווח כ-failed.
