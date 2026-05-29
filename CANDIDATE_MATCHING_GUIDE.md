# Candidate Matching & Recommendations 🎯

Feature added (2026-05-29): One-click candidate-to-job and candidate-to-client matching.

## How It Works

1. **Upload or select a candidate** from the Candidate Management page
2. **Click "🎯 התאמות"** button to open recommendations modal
3. **View matches** in two tabs:
   - **💼 משרות**: Active jobs with ≥80% match score
   - **👥 לקוחות**: Client/potential client contacts with ≥80% match score

## Matching Algorithm

### Job Matching (40-15-10 weighted score)

| Component | Points | Details |
|-----------|--------|---------|
| **Domain match** | 40 | Exact (1.0), substring/synonym (0.8-0.85), none (0.0) |
| **Security clearance** | 35 | Candidate level ≥ job requirement; same level = 1.0, higher = 0.9 |
| **Experience** | 15 | Years matched to role seniority (junior/mid/senior) |
| **Location** | 10 | Currently neutral (stub) |

**Example**: Python developer (primary_domain) + Level 1 clearance applying to:
- Python backend role requiring Level 1 → 85%+ match (domain exact, clearance exact)
- Java role requiring Level 2 → Auto-fail (clearance mismatch)

### Contact Matching (50-30-20 weighted score)

| Component | Points | Details |
|-----------|--------|---------|
| **Professional domain** | 50 | Direct match or synonym match (0.8) |
| **Security clearance** | 30 | Candidate level ≥ contact clearance level |
| **Contact status** | 20 | Client (1.0) > potential_client (0.8) |

**Example**: Python developer contacting:
- CEO at bank (clearance: Level 1, domain: Financial) → Domain mismatch, may not hit 80%
- CTO at software firm (clearance: Level 1, domain: Software) → 80%+ match (domain + clearance + status)

## Fields Used

### From `candidates` table:
- `primary_domain` — Main skill domain (Python, Java, QA, etc.)
- `secondary_domains` — Array of secondary domains
- `security_clearance_level` — "רמה 1", "רמה 2", "רמה 3", or null
- `years_of_experience` (or `years_experience`) — Total years

### From `jobs` table:
- `title` — Job title
- `required_domain` — Domain needed (e.g., "Python", "תוכנה")
- `required_security_clearance` — Clearance level
- `is_active` — Only active jobs are considered
- `priority` — Displayed in results

### From `contacts` table:
- `full_name` — Contact name
- `professional_domain` — Comma-separated domains (e.g., "Python, DevOps")
- `security_clearance_level` — Clearance level
- `contact_status` — "client" or "potential_client"

## API Endpoint

```
GET /admin/candidates/{candidate_id}/recommendations

Response:
{
  "candidate_id": "uuid",
  "candidate_name": "John Doe",
  "candidate_domain": "Python",
  "candidate_clearance": "רמה 1",
  "job_matches": [
    {
      "job_id": "uuid",
      "job_title": "Senior Python Engineer",
      "match_score": 0.92,
      "match_details": {
        "domain_match": "exact",
        "clearance_match": "meets",
        "experience_match": "5 years"
      },
      "priority": 1
    }
  ],
  "contact_recommendations": [
    {
      "contact_id": "uuid",
      "contact_name": "Alice Johnson",
      "contact_status": "client",
      "professional_domain": "Python",
      "match_score": 0.88,
      "match_details": {
        "domain_match": "exact",
        "clearance_compatibility": true,
        "contact_status": "client"
      }
    }
  ],
  "generated_at": "2026-05-29T10:30:00Z"
}
```

## Domain Synonyms Supported

The matching engine understands domain equivalences:

- **Software**: Python, Java, C++, JavaScript, TypeScript, Go, Rust, Node.js, fullstack, backend, frontend, DevOps
- **Frontend**: JavaScript, TypeScript, React, Vue, Angular
- **QA**: Testing, automation, Selenium, LoadRunner
- **Electronics**: FPGA, VHDL, Verilog, PCB, RF Design, embedded
- **Systems/DevOps**: Linux, infrastructure, networking
- **IT**: Support, helpdesk, Windows, administration

Add more in `DOMAIN_SYNONYMS` dict in `candidate_matching.py`.

## Minimum Match Score

Both job and contact matching require **≥80% match score** to display. This is configurable via the `threshold` parameter in `CandidateMatchingEngine`.

## Limits

- **Max job matches**: 5 (top by score)
- **Max contact recommendations**: 5 (top by score)

Rationale: Quality over quantity — meaningful recommendations only.

## Security Considerations

- ✅ Clearance mismatch is **hard-fail** (no score adjustment)
- ✅ Only active jobs are considered
- ✅ Only client/potential_client contacts are recommended
- ✅ Scores are transparent (all match details shown)

## Future Enhancements

- [ ] Location-based matching (distance, visa sponsorship)
- [ ] Salary range compatibility
- [ ] Keyword extraction from job description & match against skills
- [ ] Learning from user feedback (accepted vs. rejected matches)
- [ ] Batch candidate screening (upload many → get sorted recommendations)
