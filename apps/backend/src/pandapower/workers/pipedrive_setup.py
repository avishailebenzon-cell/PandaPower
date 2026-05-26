"""Phase 6.1: Pipedrive Configuration Setup & Validation."""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

import httpx

from pandapower.core.config import settings
from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)


@dataclass
class PipedriveSetupStatus:
    """Status of Pipedrive configuration."""

    api_token_set: bool = False
    api_token_valid: bool = False
    bot_user_id_set: bool = False
    bot_user_id_valid: bool = False
    api_connectivity: bool = False
    custom_fields_available: dict = None  # Will be populated with field info
    errors: list[str] = None

    def __post_init__(self):
        if self.custom_fields_available is None:
            self.custom_fields_available = {}
        if self.errors is None:
            self.errors = []

    def is_ready_for_production(self) -> bool:
        """Check if Pipedrive is ready for production use."""
        return (
            self.api_token_valid
            and self.api_connectivity
            and not self.errors
        )

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


async def validate_pipedrive_setup() -> PipedriveSetupStatus:
    """Validate current Pipedrive setup configuration.
    
    Returns:
        PipedriveSetupStatus with validation results
    """
    status = PipedriveSetupStatus()
    
    # Check if token is set
    if not settings.PIPEDRIVE_API_TOKEN:
        status.api_token_set = False
        status.errors.append("PIPEDRIVE_API_TOKEN not set in .env")
        return status
    
    status.api_token_set = True
    
    # Check if bot user ID is set
    if settings.PIPEDRIVE_BOT_USER_ID:
        status.bot_user_id_set = True
    else:
        status.errors.append("PIPEDRIVE_BOT_USER_ID not set in .env (optional but recommended)")
    
    # Test API connectivity
    try:
        client = PipedriveClient(
            api_token=settings.PIPEDRIVE_API_TOKEN,
            api_domain=settings.PIPEDRIVE_API_DOMAIN,
        )
        
        # Test with simple GET request to /v1/user (always available)
        response = await client._make_request("GET", "/v1/user")
        
        if response.get("success"):
            status.api_token_valid = True
            status.api_connectivity = True
            logger.info(f"✅ Pipedrive API token validated for user: {response.get('data', {}).get('email')}")
        else:
            status.api_token_valid = False
            status.errors.append(f"API returned error: {response.get('error')}")
            
    except Exception as e:
        status.api_connectivity = False
        status.errors.append(f"Failed to connect to Pipedrive: {str(e)}")
        logger.error(f"Pipedrive connectivity check failed: {e}")
    
    # Check for custom fields if we have connectivity
    if status.api_connectivity:
        try:
            status.custom_fields_available = await _check_custom_fields()
        except Exception as e:
            logger.warning(f"Could not check custom fields: {e}")
    
    return status


async def _check_custom_fields() -> dict:
    """Check for Pipedrive custom fields.
    
    Returns:
        Dict of available custom fields by type
    """
    client = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )
    
    custom_fields = {
        "deal_fields": {},
        "person_fields": {},
        "organization_fields": {},
    }
    
    try:
        # Get deal custom fields
        deal_fields_response = await client._make_request("GET", "/v1/dealFields")
        if deal_fields_response.get("success"):
            for field in deal_fields_response.get("data", []):
                custom_fields["deal_fields"][field.get("key")] = field.get("name")
        
        # Get person custom fields
        person_fields_response = await client._make_request("GET", "/v1/personFields")
        if person_fields_response.get("success"):
            for field in person_fields_response.get("data", []):
                custom_fields["person_fields"][field.get("key")] = field.get("name")
        
        # Get organization custom fields
        org_fields_response = await client._make_request("GET", "/v1/organizationFields")
        if org_fields_response.get("success"):
            for field in org_fields_response.get("data", []):
                custom_fields["organization_fields"][field.get("key")] = field.get("name")
                
    except Exception as e:
        logger.warning(f"Could not fetch custom fields: {e}")
    
    return custom_fields


def print_setup_checklist(status: PipedriveSetupStatus) -> str:
    """Generate a human-readable setup checklist.
    
    Args:
        status: PipedriveSetupStatus object
        
    Returns:
        Formatted checklist string
    """
    lines = [
        "\n" + "=" * 60,
        "PIPEDRIVE CONFIGURATION SETUP CHECKLIST",
        "=" * 60,
        "",
        "Phase 6.1: Authentication & Configuration Setup",
        "",
        "Configuration Items:",
        f"  {'✅' if status.api_token_set else '❌'} PIPEDRIVE_API_TOKEN set in .env",
        f"  {'✅' if status.api_token_valid else '❌'} API token is valid and working",
        f"  {'✅' if status.bot_user_id_set else '❌'} PIPEDRIVE_BOT_USER_ID set in .env",
        f"  {'✅' if status.api_connectivity else '❌'} Pipedrive API connectivity verified",
        "",
        "Next Steps:",
    ]
    
    if not status.api_token_set:
        lines.extend([
            "",
            "1. GET PIPEDRIVE API TOKEN:",
            "   - Go to: https://app.pipedrive.com/user/settings",
            "   - Find 'API' or 'Integrations' section",
            "   - Generate or copy existing API token",
            "   - Add to .env: PIPEDRIVE_API_TOKEN=<token>",
        ])
    
    if status.api_token_set and not status.bot_user_id_set:
        lines.extend([
            "",
            "2. GET PIPEDRIVE BOT USER ID:",
            "   - Option A: Use API to get current user ID",
            "   - Option B: Create a Pipedrive user account for 'Carmit Bot'",
            "   - Add to .env: PIPEDRIVE_BOT_USER_ID=<user_id>",
        ])
    
    if status.custom_fields_available:
        lines.extend([
            "",
            "3. CUSTOM FIELDS AVAILABLE:",
            f"   - Deal fields: {len(status.custom_fields_available.get('deal_fields', {}))}",
            f"   - Person fields: {len(status.custom_fields_available.get('person_fields', {}))}",
            f"   - Organization fields: {len(status.custom_fields_available.get('organization_fields', {}))}",
            "",
            "4. NEXT PHASE (6.2): Field Mapping Validation",
            "   - Create pipedrive_field_mappings table in database",
            "   - Map custom fields for:",
            "     • deal_rejection_reasons",
            "     • person_clearance_level",
            "     • person_declining_status",
            "     • job_required_clearance",
        ])
    
    if status.errors:
        lines.extend([
            "",
            "ERRORS TO RESOLVE:",
            *[f"  ⚠️  {error}" for error in status.errors],
        ])
    
    if status.is_ready_for_production():
        lines.extend([
            "",
            "✅ PIPEDRIVE CONFIGURATION READY FOR PRODUCTION",
            "You can proceed with Phase 6.2: Field Mapping",
        ])
    
    lines.extend([
        "",
        "=" * 60,
        "",
    ])
    
    return "\n".join(lines)


async def setup_pipedrive_wizard():
    """Interactive setup wizard for Pipedrive configuration.
    
    Guides user through the setup process step-by-step.
    """
    logger.info("Starting Pipedrive Configuration Wizard (Phase 6.1)")
    
    # Validate current setup
    status = await validate_pipedrive_setup()
    checklist = print_setup_checklist(status)
    
    logger.info(checklist)
    
    return status


# CLI entry point
if __name__ == "__main__":
    # Run async wizard
    status = asyncio.run(setup_pipedrive_wizard())
    exit(0 if status.is_ready_for_production() else 1)
