"""Server-side safety guard for permanently disabled platforms.

Mirrors scripts/utils/guard.py on the user-app side. The server rejects
campaigns that target X and rejects API requests that would trigger X
matching or invitations.

X is disabled across Amplifier after repeated account suspensions by X's
anti-bot detection. See docs/platform-posting-playbook.md for the full
context and Task #40 for the implementation.

DO NOT remove X from DISABLED_PLATFORMS without a verified safe method
and explicit user approval. Server and client must stay in sync.
"""

from __future__ import annotations

from typing import Iterable


DISABLED_PLATFORMS: frozenset[str] = frozenset({"x"})


def is_platform_disabled(platform: str | None) -> bool:
    """Return True if the platform is hardcoded-disabled for safety."""
    if not platform:
        return False
    return platform.strip().lower() in DISABLED_PLATFORMS


def contains_disabled(platforms: Iterable[str] | None) -> bool:
    """Return True if the iterable contains any disabled platform."""
    if not platforms:
        return False
    return any(is_platform_disabled(p) for p in platforms)


def filter_disabled(platforms: Iterable[str] | None) -> list[str]:
    """Return a list with disabled platforms stripped out."""
    if not platforms:
        return []
    return [p for p in platforms if not is_platform_disabled(p)]
