"""Status label display names for creator-facing UI (AC13 / Task #24 polish)."""

STATUS_DISPLAY = {
    "pending_invitation": "Invited",
    "content_generated": "Draft Ready",
    "posted": "Live",
    "paid": "Earned",
}


def display_status(status: str) -> str:
    """Return a human-readable label for a raw status string.

    Falls through to title-cased underscored string for unknown statuses.
    """
    return STATUS_DISPLAY.get(status, status.replace("_", " ").title())
