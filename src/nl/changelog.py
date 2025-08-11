"""
Change log utilities for tracking natural-language config adjustments.
"""

from typing import List, Dict, Any
from datetime import datetime


def create_changelog_entry(intent_action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a change log entry capturing the action, parameters, and timestamp.

    Args:
        intent_action: The name of the action derived from an intent.
        parameters: The parameters associated with the change.

    Returns:
        A dictionary representing the changelog entry, including a UTC timestamp.
    """
    return {
        "timestamp": datetime.utcnow(),
        "action": intent_action,
        "parameters": parameters,
    }


def append_changelog(changelog: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    """
    Append an entry to a changelog list. This function modifies the list in place.

    Args:
        changelog: The list of changelog entries to append to.
        entry: The changelog entry to append.
    """
    changelog.append(entry)
