"""
Pipedrive Contacts Sync Worker
Synchronizes persons from Pipedrive to the contacts table with proper categorization:
- employee (עובדים): linked to organization, no deals
- client (לקוחות): has won or open deals
- potential_client (לקוחות פוטנציאלים): everything else

This is the main entry point for contact synchronization.
"""

from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts

# Re-export for backwards compatibility
__all__ = ["sync_pipedrive_contacts"]
