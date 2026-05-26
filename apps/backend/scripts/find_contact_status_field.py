"""
Find the 'contact status' custom field in Pipedrive and its options.
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient


async def main():
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    # Get all person fields (including custom fields)
    print("Fetching person fields from Pipedrive...")
    response = await pipedrive._make_request_with_retry("GET", "/v1/personFields")

    if not response.get("success"):
        print(f"Error: {response.get('error')}")
        return

    fields = response.get("data", [])
    print(f"\nTotal person fields: {len(fields)}\n")

    # Look for the contact status field
    print("=" * 80)
    print("SEARCHING FOR CONTACT STATUS FIELD")
    print("=" * 80)

    # Print all custom fields (those with edit_flag=True usually)
    for field in fields:
        name = field.get("name", "")
        key = field.get("key", "")
        field_type = field.get("field_type", "")

        # Look for status-related fields or custom fields
        is_custom = field.get("edit_flag", False)
        name_lower = name.lower()

        # Print custom fields and any field that might be the status
        if is_custom or any(kw in name_lower for kw in ["סטטוס", "status", "type", "סוג", "קשר", "contact"]):
            print(f"\n  Name: {name}")
            print(f"  Key:  {key}")
            print(f"  Type: {field_type}")
            print(f"  Custom: {is_custom}")

            # If it has options (enum/set type), print them
            options = field.get("options")
            if options:
                print(f"  Options:")
                for opt in options:
                    print(f"    - id={opt.get('id')}: label='{opt.get('label')}'")

    # Save full field list for inspection
    with open("/tmp/pipedrive_person_fields.json", "w", encoding="utf-8") as f:
        json.dump(fields, f, indent=2, ensure_ascii=False)
    print("\n\nFull field list saved to /tmp/pipedrive_person_fields.json")

    await pipedrive.close()


if __name__ == "__main__":
    asyncio.run(main())
