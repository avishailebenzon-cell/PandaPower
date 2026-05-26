"""
Find all deal custom fields in Pipedrive with their options.
Focus on: job title, job description, job qualifications, job location,
job security clearance, deadline, priority.
"""

import asyncio
import sys
import os
import json
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient


# Keywords we are looking for (case-insensitive)
TARGET_KEYWORDS = [
    "job title", "כותרת",
    "job description", "תיאור",
    "job qualifications", "qualifications", "פירוט", "כישורים", "דרישות",
    "job location", "location", "מיקום", "מקום",
    "job security", "security clearance", "clearance", "סיווג", "בטחוני",
    "deadline", "dead line", "דדליין", "תאריך יעד",
    "priority", "עדיפות", "דחיפות",
    "company", "חברה", "ארגון", "organization",
]


def matches_target(name: str) -> bool:
    n = name.lower()
    for kw in TARGET_KEYWORDS:
        if kw.lower() in n:
            return True
    return False


async def main():
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    print("Fetching deal fields from Pipedrive...")
    response = await pipedrive._make_request_with_retry("GET", "/v1/dealFields")

    if not response.get("success"):
        print(f"Error: {response.get('error')}")
        return

    fields = response.get("data", [])
    print(f"\nTotal deal fields: {len(fields)}\n")

    # Save full field list
    with open("/tmp/pipedrive_deal_fields.json", "w", encoding="utf-8") as f:
        json.dump(fields, f, indent=2, ensure_ascii=False)
    print("Full deal fields saved to /tmp/pipedrive_deal_fields.json\n")

    # Show matching/relevant fields
    print("=" * 80)
    print("RELEVANT DEAL FIELDS")
    print("=" * 80)

    for field in fields:
        name = field.get("name", "")
        key = field.get("key", "")
        field_type = field.get("field_type", "")
        is_custom = field.get("edit_flag", False)

        # Show all custom fields + any field matching target keywords
        if is_custom or matches_target(name):
            print(f"\n  Name:   {name}")
            print(f"  Key:    {key}")
            print(f"  Type:   {field_type}")
            print(f"  Custom: {is_custom}")

            options = field.get("options")
            if options:
                print(f"  Options:")
                for opt in options:
                    print(f"    - id={opt.get('id')}: label='{opt.get('label')}'")

    await pipedrive.close()


if __name__ == "__main__":
    asyncio.run(main())
