# PandaTech Pipedrive — Complete Reference

> **Single source of truth.** Copy this whole file into any new project that needs to talk to your Pipedrive workspace.

---

## 🔑 Authentication

- **API token**: Pipedrive → User → Account → Personal preferences → API
- **Base URL**: `https://api.pipedrive.com` (or `https://pandatech.pipedrive.com`)
- **Auth method**: Query string param `?api_token=xxxxxxxxxxxx`
- **Current PandaTech token**: stored in `apps/backend/.env` as `PIPEDRIVE_API_TOKEN`

```bash
# Smoke test
curl "https://api.pipedrive.com/v1/users/me?api_token=$PIPEDRIVE_API_TOKEN" | jq .data.email
```

---

## 📦 The 3 entities

| Pipedrive | Local DB table | Bind via | Used for |
|---|---|---|---|
| **organizations** | `organizations` | `pipedrive_org_id` | Client companies |
| **persons** | `contacts` | `pipedrive_person_id` | Candidates, employees, contacts |
| **deals** | `jobs` | `pipedrive_deal_id` | Job positions |

**Sync order matters**: organizations → persons → deals (later ones depend on earlier ones via `org_id`).

---

## 🎯 PERSONS (אנשי קשר)

### Standard fields
```
id, name, first_name, last_name,
email[],   # array of {value, primary, label}
phone[],   # array of {value, primary, label}
org_id,    # int OR {value, name} dict
add_time, update_time
```

### Custom fields — **the actual PandaTech hashes**

| Hash | Hebrew name | Type |
|---|---|---|
| `ab0c233f11f664275203977ddd33194795e485b2` | סטטוס איש הקשר | single-select |
| `46b46ea96edb7a1408ac6930f25f32d704f70b53` | תחום מקצועי | multi-select |
| `ed60d224c8ddfc0a210361bdd88d9529ae22a301` | סווג בטחוני | single-select |

### Option IDs — סטטוס איש הקשר
| ID | Hebrew | English mapping |
|---|---|---|
| 4 | עובד חברה | `employee` |
| 5 | מועמד לחברה | `candidate` |
| 30 | קבלן משנה | `subcontractor` |
| 33 | לקוח פוטנציאלי | `potential_client` |
| 34 | לקוח | `client` |
| 35 | שותף עסקי | `business_partner` |
| 144 | עובד לשעבר | `former_employee` |
| 375 | מועמד בתהליך | `candidate` |

### Option IDs — סווג בטחוני
| ID | Label |
|---|---|
| 145 | רמה 1 |
| 146 | רמה 2 |
| 147 | רמה 3 |

### Option IDs — תחום מקצועי
**Dynamic** — fetch fresh each sync:
```bash
curl "https://api.pipedrive.com/v1/personFields?api_token=$TOKEN" \
  | jq '.data[] | select(.key == "46b46ea96edb7a1408ac6930f25f32d704f70b53") | .options'
```

---

## 💼 DEALS (משרות)

### Standard fields
```
id, title, status,             # 'open' | 'won' | 'lost' | 'deleted'
stage_id, pipeline_id,
value, currency,
org_id, person_id,
expected_close_date,
add_time, update_time
```

### Custom fields — **the actual PandaTech hashes**

| Hash | Hebrew name | Type |
|---|---|---|
| `c616325e1187aaa05257f6d4cd9cc3626679b23f` | כותרת משרה | text |
| `9ed8654203d45357d76e8f83ca5a8584f5f8e2fb` | תיאור משרה | text (long) |
| `5198dc3d914cb437bf95133a64809a30f69e3b02` | דרישות תפקיד | text (long) |
| `d04ed525f3ed45fb04383e07f281ad7338a30e4e` | מיקום | address |
| `9997b3547b9295447c03c98343a50f4d8d097361` | סווג בטחוני נדרש | single-select |
| `a6a8a84e518fb22fc9920f3e714a2bfaf9f488b5` | תאריך יעד | date |
| `360108d810b89e174c7ca6a3a8222eebfd278bf6` | עדיפות גיוס | single-select |

**Address note**: Pipedrive address fields produce a paired `_formatted_address` key:
- `d04ed525...` → raw structured value
- `d04ed525..._formatted_address` → human string (use this for display)

### Option IDs — עדיפות גיוס
| ID | Hebrew | Numeric (use this in code) |
|---|---|---|
| 390 | עדיפות גיוס 1 | 1 (highest) |
| 391 | עדיפות גיוס 2 | 2 |
| 392 | עדיפות גיוס 3 | 3 |
| 393 | עדיפות גיוס 4 | 4 |
| 394 | עדיפות גיוס 5 | 5 (lowest) |

### Required clearance — uses same option IDs as person clearance
`145 → רמה 1`, `146 → רמה 2`, `147 → רמה 3`

### Deal pipeline stages (recruiter workflow)
| stage_id | Phase | Meaning |
|---|---|---|
| 1 | `carmit_approved` | Routed by Carmit (AI manager) for active recruiting |
| 2 | `sent_to_tal` | With Tal for candidate screening |
| 3 | `tal_conversation` | Tal actively discussing with candidate |
| 4 | `tal_accepted` | Approved, ready for placement |
| 5 | `sent_to_elad` | With Elad for client-side placement |
| 6 | `hired` | ✓ Placed successfully (terminal) |
| 7 | `rejected_tal` | Rejected by Tal |
| 8 | `rejected_elad` | Rejected by Elad |
| 9 | `placement_failed` | Couldn't place at client (terminal) |

---

## 🏢 ORGANIZATIONS (ארגונים)

### Standard fields
```
id, name, address, country_code,
people_count, open_deals_count, won_deals_count,
add_time, update_time
```

### Custom fields
**None pinned in code yet** for the PandaTech workspace. To discover:
```bash
curl "https://api.pipedrive.com/v1/organizationFields?api_token=$TOKEN" \
  | jq '.data[] | select(.edit_flag == true) | {key, name, field_type}'
```
(`edit_flag: true` = custom field, `false` = built-in.)

---

## 🆔 Deterministic UUID generation

PandaPower uses UUID v5 to generate stable local IDs from Pipedrive IDs — so re-syncs never create duplicates.

```python
import uuid

# DO NOT CHANGE these namespaces across deployments
ORG_NAMESPACE     = uuid.UUID("12345678-1234-5678-1234-567812345678")
PERSON_NAMESPACE  = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
DEAL_NAMESPACE    = uuid.UUID("11111111-2222-3333-4444-555555555555")

def pipedrive_org_id_to_uuid(pipedrive_org_id: int) -> str:
    return str(uuid.uuid5(ORG_NAMESPACE, f"pipedrive_org:{pipedrive_org_id}"))

# Same input → same UUID. Forever. Across machines. Across databases.
```

---

## 🏗️ Sync architecture (TL;DR)

```
┌────────────────────────────────┐
│  Scheduler ticks every 60s     │  background asyncio.Task in main.py
│  → reads pipedrive_sync_       │
│    schedule table              │
│  → fires due workers           │
└──────────────┬─────────────────┘
               │
       ┌───────┼───────┐
       ▼       ▼       ▼
   ┌──────┐ ┌────┐ ┌──────┐
   │ orgs │ │perm│ │deals │   ← run in dependency order
   └──┬───┘ └─┬──┘ └──┬───┘
      │       │       │
      └───────┼───────┘
              ▼
      ┌───────────────┐
      │ PipedriveClient│   ← retries, rate limit, pagination
      └───────────────┘
```

### Per-entity config (in DB table `pipedrive_sync_schedule`)
- `sync_enabled` — toggle on/off
- `sync_interval_minutes` — minimum gap between runs
- `sync_days` — `[Sun,Mon,Tue,Wed,Thu,Fri,Sat]` booleans
- `sync_time` — `"HH:MM"` daily start gate (NULL = any time)
- `last_sync_at` — updated after each successful run

### Sync history (`pipedrive_sync_log`)
- Every run logs start time, end time, records processed, errors
- Stale `in_progress` rows >30min should be auto-marked `failed` by a cleanup job

---

## ⚠️ Production gotchas (we hit ALL of these)

1. **`org_id` shape varies** — sometimes `int`, sometimes `{value: int, name: str}`. Use `extract_id()` helper.

2. **Multi-select format** — comes back as `"4,33,144"` (comma-separated option IDs as STRING). Split, parse, look up.

3. **Rate limit** — ~100 req/10s. Respect `Retry-After` header on 429s.

4. **No reliable "modified since"** — Pipedrive doesn't fire `update_time` on custom field changes. Use webhooks for fast updates + full pull on slow cadence.

5. **Hash stability** — custom field hashes are stable PER WORKSPACE. They're NOT shared across Pipedrive accounts. Re-discover when moving to a new workspace.

6. **Address formatted_address suffix** — address fields create TWO keys, the bare key + `_formatted_address`. Use the formatted one for display.

7. **Workspace timezone** — Pipedrive serves all timestamps in workspace TZ. Normalize to UTC before storing.

8. **`stage_id` is workspace-specific** — the numbers 1-9 in this doc match the PandaTech recruiter pipeline. Other pipelines have different IDs.

---

## 🚀 Quick start in a new project

### 1. Copy the skill
The reusable knowledge lives in `~/.claude/skills/pipedrive-integration/`. Any Claude Code instance you start will be able to find it via Skill triggering.

### 2. Install in your project
```bash
cd your-new-project
pip install httpx supabase  # supabase optional if you're not using it
```

### 3. Drop in the helpers
```bash
cp ~/.claude/skills/pipedrive-integration/code_snippets.py your-new-project/lib/pipedrive.py
```

### 4. Apply the schema
```bash
psql your_db < ~/.claude/skills/pipedrive-integration/db_schema.sql
```

### 5. Run the smoke test
```bash
PIPEDRIVE_API_TOKEN=xxx python lib/pipedrive.py
```

You'll see:
- Auth confirmation
- Counts of persons / deals / orgs
- All custom fields with their options

### 6. Build your sync
```python
from lib.pipedrive import (
    PipedriveClient,
    build_contact_row, build_job_row,
    pipedrive_org_id_to_uuid,
)

async def sync():
    client = PipedriveClient(api_token=os.getenv("PIPEDRIVE_API_TOKEN"))
    persons = await client.get_all_persons()
    for p in persons:
        row = await build_contact_row(p, domain_options={})
        await db.table("contacts").upsert(row, on_conflict="pipedrive_person_id").execute()
```

---

## 📚 Files in this knowledge bundle

Located at `~/.claude/skills/pipedrive-integration/`:

| File | Purpose |
|---|---|
| `SKILL.md` | Triggers Claude to use this knowledge (auto-loaded by Skill system) |
| `pipedrive_fields.md` | Same field reference as above, formatted for Claude consumption |
| `sync_architecture.md` | Detailed walkthrough of scheduler, workers, retries, webhooks |
| `code_snippets.py` | All helper functions ready to copy-paste |
| `db_schema.sql` | The Supabase/PostgreSQL schema |

---

## 🔄 When fields change in Pipedrive

If you add/rename a custom field in Pipedrive:

1. Discover the new hash:
   ```bash
   curl "https://api.pipedrive.com/v1/personFields?api_token=$TOKEN" \
     | jq '.data[] | select(.edit_flag == true) | {key, name, options}'
   ```
2. Update **both**:
   - `~/.claude/skills/pipedrive-integration/pipedrive_fields.md`
   - `~/.claude/skills/pipedrive-integration/code_snippets.py` (the `FIELD_*` constants)
3. Commit the change so other devs (and future Claude sessions) inherit it.

---

## ❤️ Why this skill structure?

By living in `~/.claude/skills/`, this knowledge is automatically available to **every Claude Code session you start** — across all projects, all repos, all working directories. No more re-explaining the field hashes to a fresh Claude. Just say "talk to Pipedrive" and the skill fires.
