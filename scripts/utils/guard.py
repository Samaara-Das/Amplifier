"""Safety guard for permanently disabled platforms.

X (Twitter) is disabled across all Amplifier automation after repeated
account suspensions by X's anti-bot detection. Human emulation (typing
delays, scrolling, persistent sessions, stealth flags) does not defeat
the detection.

Three X account incidents (see memory/project_x_account_locked.md):
  - Original account: permanently locked
  - 2026-03-24: replacement account first block during testing
  - 2026-04-14: replacement account suspended during Amplifier test posting

DO NOT remove X from DISABLED_PLATFORMS without a verified safe method
(X API v2, stealth browser framework like camoufox, etc.) AND explicit
user approval. Shipping X support today means getting paying users
suspended.

Related: Task #40 in task-master.
"""

from __future__ import annotations

from typing import Iterable


# Source of truth — platforms blocked at the code level, independent of
# any config file. Use lowercase names.
DISABLED_PLATFORMS: frozenset[str] = frozenset({"x"})


def is_platform_disabled(platform: str | None) -> bool:
    """Return True if the platform is hardcoded-disabled for safety."""
    if not platform:
        return False
    return platform.strip().lower() in DISABLED_PLATFORMS


def guard_platform(platform: str | None, action: str = "access") -> None:
    """Raise ValueError if the platform is disabled.

    Call at every entry point that could launch automation (posting,
    scraping, metric collection, content generation, login).

    Args:
        platform: Platform identifier (e.g., "x", "linkedin").
        action: Short description of the attempted operation, for logs.

    Raises:
        ValueError: If the platform is in DISABLED_PLATFORMS.
    """
    if is_platform_disabled(platform):
        raise ValueError(
            f"Platform {platform!r} is permanently disabled for safety "
            f"(action: {action}). See memory/project_x_account_locked.md "
            f"and Task #40."
        )


def filter_disabled(platforms: Iterable[str] | None) -> list[str]:
    """Return a list with disabled platforms stripped out.

    Use this on every hardcoded platform iteration list in the codebase.
    Accepts any iterable (list, tuple, set, dict_keys) and returns a
    stable-ordered list preserving the original order.
    """
    if not platforms:
        return []
    return [p for p in platforms if not is_platform_disabled(p)]
