# PandaPower — Phase 10.5 Claude Code Prompt

> **⭐ Manual Security Clearance Overrides** — Bridge phase between Pandi (Phase 10) and Rami (Phase 11).
>
> סשן אחד בלבד. מטרה: לאפשר אדמין לסמן ידנית את ה-clearance של מועמדים שהוא מכיר אישית.
>
> **למה זה כאן ולא חלק מ-Phase 11?**
> - זה משפיע על schema של candidates → שינוי בסיסי
> - זה משפיע על LLM workflow → צריך לעדכן workers קיימים
> - זה prerequisite להצלחת רמי — בלי האפשרות לסמן ידנית, רמי יתחיל עם data חלקי

---

## תלות

- ✅ Phase 1-9 סגורים.
- ⏸️ Phase 10 (Pandi) — לא חובה לסיים לפני, אבל אם הוא בעבודה, סיים אותו קודם כי הוא מוסיף `candidate_number` שמסך ה-overrides ישתמש בו לזיהוי.
- 🚧 Phase 11 (Rami) — **דחה אותו** עד אחרי הסיום הזה.

---

## הכנות מקדימות לפני סשן 33

1. ✅ **רשימת המועמדים הידועים** — תכין CSV עם 2 עמודות: `email_or_phone_or_name`, `clearance_level`. ה-script ב-Phase 10.5 ייקח את ה-CSV ויעדכן את כל המועמדים. אם אין לך CSV עדיין — תוכל גם להזין ידנית מה-UI אחרי שהפיצ'ר עולה.
2. ✅ **רשימת clearance levels מוסכמים** — וודא שכל הערכים תואמים ל-enum: `'none' | 'confidential' | 'secret' | 'top_secret' | 'highest'`. אם יש לך ערכים אחרים — נצטרך להחליט אם להרחיב את ה-enum.

---

## איך להשתמש בקובץ הזה

זהה לפאזות קודמות. סשן אחד = משימה ממוקדת = PR אחד. בכל סשן חדש: `/clear`, ואז ודא ש-CLAUDE.md (גרסה 1.6) נקרא.

---

## Session 33 — Manual Security Clearance Overrides

### Prompt להעתיק לתוך Claude Code:

```
שלום קלוד. אני ב-Phase 10.5 של PandaPower — תוספת חשובה שמאפשרת לאדמין לדרוס את ה-LLM בנושא של security clearance. קרא את CLAUDE.md סעיף 7.4 במלואו, וגם 5.1 (טבלת candidates — שדות חדשים).

⚠️ **כללי זהב של Phase 10.5:**
1. **Backwards compatible** — המערכת בייצור. כל candidate קיים חייב להמשיך לעבוד. ה-migration מוסיף שדות עם DEFAULT, לא מסיר/משנה.
2. **Single source of truth** — `candidates.security_clearance_level` נשאר השדה היחיד שכל הקוד קורא ממנו. ה-source נוסף רק כ-metadata.
3. **Audit trail** — כל override נשמר ב-`agent_logs`.
4. **Bulk operations שימושיות** — אבישי צריך לסמן 30-50 מועמדים מראש. ה-UX חייב להיות יעיל.

# מטרת הסשן

1. DB migration: 4 עמודות חדשות ל-candidates.
2. עדכון LLM workflow: cv_analyze worker מכבד override קיים.
3. API: 5 endpoints חדשים (single override, clear, bulk, CSV import, history).
4. UI: 4 נקודות מגע חדשות (profile button, bulk action בlist, manual upload checkbox, indicators ברחבי המערכת).
5. Telegram bot: 3 פקודות חדשות.
6. Pre-launch import script.

🚫 אסור בסשן הזה:
- אל תיגע ב-cv_analysis prompt עצמו (LLM workflow logic only, לא ה-prompt).
- אל תשנה schema של candidates מעבר ל-4 עמודות שצויינו.
- אל תיישם re-analyze פר-candidate כאן (זה Phase 3 functionality קיימת — רק תוודא ש-override מכבד).

# סקופ

## Backend

### 1. DB Migration
0019_add_clearance_override_columns.sql:
```sql
ALTER TABLE candidates ADD COLUMN security_clearance_source TEXT 
  DEFAULT 'llm_inferred'
  CHECK (security_clearance_source IN ('llm_inferred', 'admin_override', 'manual_entry'));

ALTER TABLE candidates ADD COLUMN security_clearance_override_reason TEXT;
ALTER TABLE candidates ADD COLUMN security_clearance_override_by_user_id UUID REFERENCES users(id);
ALTER TABLE candidates ADD COLUMN security_clearance_override_at TIMESTAMPTZ;

-- backfill: כל ה-candidates הקיימים → source='llm_inferred'
UPDATE candidates SET security_clearance_source = 'llm_inferred' WHERE security_clearance_source IS NULL;

-- אינדקס שיעזור ל-Rami למצוא Level 1 מהר
CREATE INDEX idx_candidates_clearance_source ON candidates(security_clearance_level, security_clearance_source);
```

### 2. Update cv_analyze worker
src/pandapower/workers/cv_analyze.py (Phase 3 Session 9):

```python
async def analyze_cv(cv_file_id):
    cv_file = await db.get(CVFile, cv_file_id)
    candidate = await db.get(Candidate, cv_file.candidate_id) if cv_file.candidate_id else None
    
    llm_result = await anthropic_client.analyze_cv(cv_file.raw_text)
    
    # שמור LLM analysis מלא תמיד
    cv_file.llm_analysis = llm_result.model_dump()
    cv_file.parse_status = 'analyzed'
    
    if candidate:
        # עדכן שאר השדות
        candidate.cv_summary = llm_result.summary
        candidate.years_experience = llm_result.years_experience
        candidate.primary_domain = llm_result.primary_domain
        # ... כל השדות מ-Phase 3
        
        # ⭐ KEY CHANGE: עדכן clearance רק אם אין override
        if candidate.security_clearance_source != 'admin_override' and \
           candidate.security_clearance_source != 'manual_entry':
            candidate.security_clearance_level = llm_result.security_clearance.level
            candidate.security_clearance_confidence = llm_result.security_clearance.confidence
            candidate.security_clearance_evidence = llm_result.security_clearance.evidence
            candidate.security_clearance_source = 'llm_inferred'
        # else: השאר את ה-override
    
    await db.commit()
```

**הערה חשובה:** ה-LLM **עדיין רץ** מלא — הוא חולץ skills, experience, summary. רק ה-clearance fields לא מועברים ל-candidate אם יש override. זה לא חוסך LLM cost — אבל מבטיח איכות.

### 3. New API endpoints
src/pandapower/routers/candidates.py — הרחב:

```python
# Override single candidate
@router.post("/candidates/{candidate_id}/override-clearance")
async def override_clearance(
    candidate_id: UUID,
    body: ClearanceOverrideRequest,  # {level: str, reason: str}
    current_user: User = Depends(require_role(['admin', 'manager'])),
):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404)
    
    previous_value = {
        'level': candidate.security_clearance_level,
        'source': candidate.security_clearance_source,
    }
    
    candidate.security_clearance_level = body.level
    candidate.security_clearance_source = 'admin_override'
    candidate.security_clearance_override_reason = body.reason
    candidate.security_clearance_override_by_user_id = current_user.id
    candidate.security_clearance_override_at = datetime.utcnow()
    # נמחק confidence/evidence (לא רלוונטי לoverride)
    candidate.security_clearance_confidence = None
    candidate.security_clearance_evidence = None
    
    # Audit log
    await create_agent_log(
        agent_code='admin_override',
        action='override_clearance',
        related_candidate_id=candidate_id,
        input_payload=previous_value,
        output_payload={'level': body.level, 'reason': body.reason},
        triggered_by_user_id=current_user.id,
    )
    
    await db.commit()
    return {"ok": True, "candidate_id": candidate_id}


# Clear override (revert to LLM)
@router.post("/candidates/{candidate_id}/clear-override")
async def clear_override(
    candidate_id: UUID,
    current_user: User = Depends(require_role(['admin', 'manager'])),
):
    candidate = await db.get(Candidate, candidate_id)
    
    if candidate.security_clearance_source == 'llm_inferred':
        return {"ok": True, "message": "No override to clear"}
    
    # Reset override fields
    candidate.security_clearance_source = 'llm_inferred'
    candidate.security_clearance_override_reason = None
    candidate.security_clearance_override_by_user_id = None
    candidate.security_clearance_override_at = None
    # ה-level הנוכחי נשאר עד שה-LLM ירוץ מחדש
    
    # Queue re-analyze על ה-CV האחרון
    latest_cv = await db.scalar(select(CVFile).where(
        CVFile.candidate_id == candidate_id
    ).order_by(CVFile.created_at.desc()).limit(1))
    
    if latest_cv:
        queue_task('analyze_cv', cv_file_id=latest_cv.id)
    
    # Audit
    await create_agent_log(
        agent_code='admin_override',
        action='clear_override',
        related_candidate_id=candidate_id,
        triggered_by_user_id=current_user.id,
    )
    
    await db.commit()
    return {"ok": True, "re_analyze_queued": latest_cv is not None}


# Bulk override
@router.post("/candidates/bulk-override-clearance")
async def bulk_override(
    body: BulkOverrideRequest,  # {candidate_ids: list[UUID], level: str, reason: str}
    current_user: User = Depends(require_role(['admin', 'manager'])),
):
    if len(body.candidate_ids) > 200:
        raise HTTPException(400, "Max 200 candidates per bulk operation")
    
    updated = 0
    errors = []
    for candidate_id in body.candidate_ids:
        try:
            # ... same as single, but in loop
            updated += 1
        except Exception as e:
            errors.append({"candidate_id": str(candidate_id), "error": str(e)})
    
    return {"ok": True, "updated": updated, "errors": errors}


# Get clearance history of a candidate
@router.get("/candidates/{candidate_id}/clearance-history")
async def get_clearance_history(candidate_id: UUID):
    logs = await db.scalars(select(AgentLog).where(
        AgentLog.related_candidate_id == candidate_id,
        AgentLog.action.in_(['override_clearance', 'clear_override']),
    ).order_by(AgentLog.created_at.desc())).all()
    
    return {"events": logs}


# CSV import
@router.post("/candidates/import-clearance-csv")
async def import_clearance_csv(
    file: UploadFile,
    current_user: User = Depends(require_role(['admin'])),
):
    """
    CSV format: candidate_identifier, level, reason
    candidate_identifier יכול להיות: candidate_number, email, או phone (E.164).
    """
    rows = parse_csv(file)
    results = {"updated": 0, "not_found": [], "errors": []}
    
    for row in rows:
        try:
            # נסה למצוא לפי כל אחד מ-3 הזיהויים
            candidate = await find_candidate_flexible(row.candidate_identifier)
            if not candidate:
                results["not_found"].append(row.candidate_identifier)
                continue
            
            # Apply override (same logic)
            # ...
            results["updated"] += 1
        except Exception as e:
            results["errors"].append({"row": row, "error": str(e)})
    
    return results
```

### 4. Pre-launch import script
scripts/import_known_level1.py:
```python
"""
Standalone script to import known Level 1 candidates from CSV.
Usage:
    uv run python scripts/import_known_level1.py path/to/known_level1.csv
"""
import csv
import asyncio
from pandapower.core.db import get_session
# ... call the bulk override logic

if __name__ == "__main__":
    asyncio.run(main())
```

ה-script מוסיף "system_user" placeholder אם אין אדמין רגיל זמין במהלך bootstrap.

### 5. Manual CV Upload — תוספת
src/pandapower/routers/cv_upload.py (Phase 3 Session 11):

הוסף לתוך POST /candidates/upload-cv:
```python
# Optional manual clearance entry
if body.manual_clearance_level:
    # שמור את הbיט הזה — יחול אחרי שה-candidate נוצר/נמצא
    manual_clearance = body.manual_clearance_level
    manual_clearance_reason = body.manual_clearance_reason or "Set during manual upload"

# ... after candidate persistence:
if manual_clearance and candidate:
    candidate.security_clearance_level = manual_clearance
    candidate.security_clearance_source = 'manual_entry'
    candidate.security_clearance_override_reason = manual_clearance_reason
    candidate.security_clearance_override_by_user_id = current_user.id
    candidate.security_clearance_override_at = datetime.utcnow()
    await db.commit()
```

### 6. Telegram bot extensions
ב-bot handlers (Phase 6.5):
- `/override_clearance <candidate_number> <level> [reason]` — set override
- `/clear_override <candidate_number>` — clear
- `/show_clearance <candidate_number>` — show current + source + reason

## Frontend

### 1. /candidates/:id profile page — תוספת
ליד שדה security_clearance, הוסף:
- Badge קטן ליד הערך:
  - `security_clearance_source='llm_inferred'` → "🤖 LLM" אפור
  - `'admin_override'` → "👤 Admin" כחול, hover מציג reason + override_by_user_name + date
  - `'manual_entry'` → "📝 Manual" ירוק

- כפתור "Override" (admin/manager only):
  - Modal עם:
    - Select level (dropdown מ-clearance enum)
    - Reason textarea (required)
    - Preview של current value vs new
    - "Save Override" / "Cancel" buttons
- אם source != 'llm_inferred':
  - כפתור נוסף "Clear Override" (admin/manager only):
    - Confirmation dialog "ההערך יחזור להיות בקרת LLM. ה-CV ינותח מחדש. להמשיך?"

### 2. /candidates list — Bulk override
- Checkbox column בכל שורה.
- Toolbar עם "Selected: N" עם actions:
  - "Bulk Override Clearance" (admin/manager only)
- Modal:
  - מציג רשימת N candidates שנבחרו
  - Select level (משותף לכולם)
  - Reason textarea (משותף)
  - "Apply to N candidates" button → calls bulk-override API.
- Display indicators (🤖/👤/📝) בעמודה של clearance.

**Bonus filter:** "Filter by clearance source" — לסנן רק admin_override / manual_entry — שימושי לאדמין לראות מה הוא סימן.

### 3. CSV Import UI
`/candidates` → toolbar action "📥 Import clearance from CSV" (admin only):
- Modal:
  - File upload (CSV)
  - Format help: "CSV columns: identifier (email/phone/candidate_number), level, reason"
  - "Preview" — מציג 5 שורות ראשונות + valid/invalid
  - "Import" — שולח ל-API, מציג progress
- Result: "Updated N, Not found: list, Errors: list".

### 4. Manual CV Upload Dialog — תוספת
ב-`UploadCVDialog` (Phase 3 Session 11):
- מתחת לשדות הקיימים, הוסף section אופציונלי:
  - Checkbox: "אני מכיר את המועמד הזה ויודע את רמת הסיווג שלו"
  - אם נבחר → reveals:
    - Select clearance level (dropdown)
    - Reason textarea (optional, default "Set during manual upload by {user_name}")
- בupload — שולח גם את ה-manual clearance fields ל-API.

### 5. Indicators ברחבי המערכת
בכל מקום שמציג את ה-clearance של candidate:
- `/candidates` list — small badge ליד הערך
- `/matches/:id` candidate snapshot
- `/agents/{code}` recent matches table
- `/agents/rami` — UI יציין מיהם override (חשוב כי רמי משתמש בערך הזה)
- `/referrals` — לא רלוונטי (כי המידע אנונימי לפי פנדי)

### 6. Bulk import flow (admin)
מסך admin חדש `/admin/clearance-bulk-import`:
- מסביר את הגישה ב-2 דרכים:
  1. **From candidates list:** select candidates → bulk action
  2. **From CSV:** upload file
- Recent imports history — לראות מה הוטמע לאחרונה.
- Stats: כמה candidates עם override כעת, חתך לפי level.

# מה אסור לעשות בסשן הזה

❌ אל תיגע ב-LLM prompt של cv_analysis. הוא מחזיר את ה-clearance כרגיל; הshיכמן רק לא מעדכן את ה-candidate.
❌ אל תוסיף מנגנון override לשדות אחרים (skills, domain, וכו'). זה רק על clearance.
❌ אל תיישם automation שעקיפת LLM הופכת לרמה 1 — האדמין חייב לאשר במפורש.

# Acceptance Criteria

1. **Migration עוברת נקי** על staging. כל candidate קיים מקבל `source='llm_inferred'`.

2. **Single override end-to-end:**
   - Go to /candidates/:id of a candidate with clearance='secret', source='llm_inferred'.
   - Click "Override" → set to 'top_secret', reason "מכיר אישית, יחידה X" → Save.
   - Verify DB: level='top_secret', source='admin_override', reason saved, override_by_user_id=current.
   - Verify UI badge: "👤 Admin" appears, hover shows tooltip.
   - Trigger re-analyze of the CV → verify that LLM result didn't overwrite the override.

3. **Clear override end-to-end:**
   - On overridden candidate, click "Clear Override".
   - Verify: source='llm_inferred', re-analyze task queued.
   - After re-analyze: level is back to LLM-determined value.

4. **Bulk override end-to-end:**
   - Select 5 candidates in /candidates list.
   - Click "Bulk Override" → set all to 'secret', reason "Pilot batch".
   - Verify all 5 updated.

5. **CSV import:**
   - Create test.csv with 3 rows (mixed identifier types: 1 by candidate_number, 1 by email, 1 by phone).
   - Upload via UI.
   - Verify all 3 found and updated. Verify error reporting for invalid rows.

6. **Manual upload with manual clearance:**
   - Upload a new CV through Manual CV Upload dialog.
   - Check "I know this candidate's clearance" → select 'top_secret'.
   - After upload + LLM analysis: verify candidate.security_clearance_level='top_secret', source='manual_entry'.
   - LLM didn't override.

7. **Telegram commands:**
   - `/override_clearance C000123 top_secret "מכיר"` → works.
   - `/show_clearance C000123` → shows "👤 Admin Override: top_secret, מכיר".
   - `/clear_override C000123` → works.

8. **Rami integration (smoke test, optional):**
   - אם Rami כבר עלה (Phase 11): bulk override candidate ל-top_secret → trigger rami_run_for_new_candidate → rami מוצא את המועמד.

9. **Audit trail:**
   - Verify agent_logs has rows with agent_code='admin_override', action='override_clearance'.

10. **CI ירוק.**

# סיום

סכם:
- כמה candidates יש כעת עם override (אבישי בטח יסמן הרבה)
- אם זוהו edge cases (לדוגמה candidate שיש לו 2 CVs ובאחד LLM חושב X ובשני Y)
- מה אבישי צריך לדעת על workflow שלו לפני שמתחיל את Phase 11

תתחיל.
```

### בדיקות שלך אחרי הסשן
- [ ] בצע override על מועמד בודד מ-UI. בדוק ש-LLM re-analyze לא דורס.
- [ ] **חשוב:** הכן CSV של 30-50 מועמדים שאתה יודע שהם רמה 1. הרץ את ה-import.
- [ ] בדוק שה-badges מופיעות במסכים השונים.
- [ ] בדוק Telegram bot commands.
- [ ] **merge ה-PR.** עכשיו אתה מוכן ל-Phase 11 (Rami) עם data איכותי.

---

## ✅ Phase 10.5 — סיכום

יש לך עכשיו:
- ✅ יכולת לדרוס ידנית את ה-clearance של כל candidate
- ✅ bulk override של מועמדים רבים בבת אחת
- ✅ CSV import לאוכלוסה קיימת
- ✅ UI indicators ברורים (🤖 / 👤 / 📝)
- ✅ Audit trail מלא של כל שינוי
- ✅ Telegram bot integration
- ✅ LLM workflow מכבד את ה-override

**עכשיו רמי יקבל data שלם ומדויק.** 🎯

---

🐼💡⭐ **בהצלחה!**
