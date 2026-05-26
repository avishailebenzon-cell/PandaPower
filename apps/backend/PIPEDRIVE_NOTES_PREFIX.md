# Pipedrive Notes Prefix Policy

## Overview

All notes written to Pipedrive from PandaPower system are prefixed with: **🐼 [PandaPowerBot]**

This ensures:
- ✅ Clear audit trail - easy to identify system-generated vs manual notes
- ✅ Accountability - know which system wrote each note
- ✅ Debugging - quick visual identification in Pipedrive
- ✅ Filtering - can programmatically filter bot notes vs human notes

---

## Where Notes Are Written

### 1. Carmit Rejection Notes
**File:** `/apps/backend/src/pandapower/workers/carmit.py`  
**Trigger:** Match fails quality gates  
**Content:** Gate results, candidate/job info, decision reasoning  
**Example:**
```
🐼 [PandaPowerBot] ❌ Carmit Orchestrator - Match Rejected

Candidate: David Cohen
Position: Senior Python Developer
Match Score: 0.65

Failed Gates:
  - quality_threshold: Match score too low (0.65 < 0.70)

Decision Reasoning: Quality gate check failed
...
```

### 2. Recruiter Decision Notes
**File:** `/apps/backend/src/pandapower/workers/pipedrive_recruiter_workflow.py`  
**Trigger:** Tal or Elad makes decision on match  
**Content:** Recruiter name, decision (accepted/rejected), reasoning  
**Example:**
```
🐼 [PandaPowerBot] TAL Decision: accepted

Reason: Candidate verified and match confirmed
```

### 3. Other System Notes
Any other notes written by the system will automatically include the prefix.

---

## Implementation Details

### Automatic Prefix Addition

All notes go through the central `write_note_to_deal()` function in pipedrive.py:

**File:** `/apps/backend/src/pandapower/integrations/pipedrive.py`

```python
async def write_note_to_deal(self, deal_id: str, note_text: str) -> dict:
    """Write a note to a deal with automatic PandaPowerBot prefix."""
    endpoint = f"/v1/deals/{deal_id}/notes"
    # Add PandaPowerBot prefix to all notes for audit trail
    prefixed_note = f"🐼 [PandaPowerBot] {note_text}"
    payload = {"content": prefixed_note}
    response = await self._make_request("POST", endpoint, body=payload)
    return response.get("data", {})
```

**Key points:**
- All calls to `write_note_to_deal()` automatically add the prefix
- No need to modify individual note creation code
- Consistent format across all system-generated notes
- Easy to update prefix globally if needed

---

## Filtering Notes

### Get Only PandaPowerBot Notes

The `get_deal_rejections()` method automatically filters for PandaPowerBot notes:

```python
async def get_deal_rejections(self, deal_id: str) -> list[dict]:
    """Get past rejection reasons - only from PandaPowerBot."""
    # ... fetch notes from Pipedrive ...
    
    # Only include rejection notes from PandaPowerBot
    if "[pandapowerbot]" in content_lower and ("reject" in content_lower ...):
        rejections.append(note)
    
    return rejections
```

### Query Notes in Pipedrive UI

```
Note content contains "[PandaPowerBot]"
```

This will show only system-generated notes, filtering out manual notes from recruiters.

---

## Audit Trail Benefits

### For Debugging
- Quickly identify which system wrote a note
- Trace match decision history
- Understand what information system had when deciding

### For Compliance
- Clear record of automated decisions
- Timestamp included in note content
- Gate results and reasoning documented
- Matches decisions to database audit trail

### For Business Intelligence
- Filter bot notes vs human notes
- Analyze system decision patterns
- Correlate system decisions with outcomes
- Identify edge cases or issues

---

## Format Specification

### Prefix Format
```
🐼 [PandaPowerBot]
```

**Components:**
- 🐼 Panda emoji (matches PandaPower branding)
- [PandaPowerBot] (clear identifier in brackets)
- Space before note content

### Example Notes

**Format 1: Rejection Note**
```
🐼 [PandaPowerBot] ❌ Carmit Orchestrator - Match Rejected
[detailed info...]
```

**Format 2: Decision Note**
```
🐼 [PandaPowerBot] TAL Decision: accepted
[reason...]
```

---

## Changes Made

### File: pipedrive.py
- **Function:** `write_note_to_deal()`
- **Change:** Added automatic prefix to all notes
- **Backward Compatible:** Yes - only affects new notes

- **Function:** `get_deal_rejections()`
- **Change:** Updated to filter for [PandaPowerBot] prefix
- **Reason:** Ensures we only track system-generated rejections

### Files Affected
All of the following now automatically include prefix:
- `workers/carmit.py` - Rejection notes
- `workers/pipedrive_recruiter_workflow.py` - Decision notes
- Any future code calling `write_note_to_deal()`

---

## Testing the Prefix

### Manual Test
```bash
# Create a test note
curl -X POST \
  https://api.pipedrive.com/v1/deals/{deal_id}/notes \
  -H "Content-Type: application/json" \
  -d '{"content": "🐼 [PandaPowerBot] Test note"}'

# Verify it appears with prefix in Pipedrive UI
```

### Programmatic Test
```python
# Notes written through PandaPower will have prefix
note = await pipedrive_client.write_note_to_deal(deal_id, "Test message")
print(note["content"])  # Output: 🐼 [PandaPowerBot] Test message
```

---

## Future Enhancements

### Optional Enhancements
1. Different prefixes for different systems
   - 🐼 [PandaPowerBot] for main system
   - 🎯 [CarmitBot] for Carmit-specific notes
   - 📞 [RecruiterBot] for recruiter workflow notes

2. Structured metadata
   - `[Module: carmit]` instead of just `[PandaPowerBot]`
   - `[Version: 1.0]` to track system version

3. Filtering by type in UI
   - Tag system: `#system`, `#automated`, `#audit`
   - Easy to create Pipedrive filters

---

## FAQ

**Q: Can I manually add this prefix to human notes?**  
A: Not recommended. The prefix indicates system-generated notes. Manual notes should be written without the prefix.

**Q: What if I need to edit a note?**  
A: The prefix is added during creation. If you edit a note in Pipedrive, the prefix will remain.

**Q: Can the prefix be changed?**  
A: Yes, change it in `pipedrive.py` line 92. All future notes will use the new prefix.

**Q: How do I distinguish between Carmit and Recruiter notes?**  
A: Currently, both use the same prefix. You can:
1. Read the note content (includes module name)
2. Check the timestamp
3. Enhance with different prefixes (see Future Enhancements)

**Q: Does this affect API queries for notes?**  
A: No, the prefix is just text content. All queries continue to work normally.

---

## Summary

✅ **All notes are now prefixed** with 🐼 [PandaPowerBot]  
✅ **Automatic implementation** - no need to modify note-writing code  
✅ **Backward compatible** - only affects new notes  
✅ **Audit trail** - clear identification of system-generated notes  
✅ **Easy filtering** - query notes by prefix in Pipedrive  
✅ **Extensible** - can add different prefixes for different modules in future  

The system now has a clear, auditable trail of all automated decisions in Pipedrive!
