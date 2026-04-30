"""Fallback selector chains for Playwright — try multiple selectors before failing.

Inspired by AmpliFire v3's NodeFinder.kt. Each element can have 3+ selectors;
the chain tries each one and returns the first match. A single broken selector
no longer kills posting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from engine.script_parser import Selector, SelectorTarget

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page

logger = logging.getLogger(__name__)


class AllSelectorsFailedError(Exception):
    """Raised when every selector in a fallback chain fails."""

    def __init__(self, selectors: list[Selector], timeout_ms: int):
        tried = ", ".join(f"{s.by}={s.value!r}" for s in selectors)
        super().__init__(f"All selectors failed (timeout={timeout_ms}ms): [{tried}]")
        self.selectors = selectors


def _selector_to_locator(page: Page, sel: Selector) -> Locator:
    """Convert a Selector dataclass to a Playwright Locator."""
    by = sel.by
    val = sel.value

    if by == "css":
        return page.locator(val)
    elif by == "text":
        return page.get_by_text(val)
    elif by == "role":
        # value format: "button" or "button:Post" (role:name)
        if ":" in val:
            role, name = val.split(":", 1)
            return page.get_by_role(role, name=name)
        return page.get_by_role(val)
    elif by == "testid":
        return page.get_by_test_id(val)
    elif by == "aria_label" or by == "aria-label":
        return page.locator(f'[aria-label="{val}"]')
    elif by == "xpath":
        return page.locator(f"xpath={val}")
    elif by == "placeholder":
        return page.get_by_placeholder(val)
    else:
        # Default: treat value as CSS selector
        return page.locator(val)


async def find_element(
    page: Page,
    target: SelectorTarget,
    timeout_ms: int = 3000,
) -> Locator:
    """Find an element using a fallback chain of selectors.

    Tries each selector in order. Returns the first Locator that resolves
    to a visible element. Raises AllSelectorsFailedError if none match.
    """
    if not target or not target.selectors:
        raise ValueError("SelectorTarget has no selectors")

    per_selector_timeout = max(500, timeout_ms // max(len(target.selectors), 1))

    for i, sel in enumerate(target.selectors):
        try:
            locator = _selector_to_locator(page, sel)
            await locator.first.wait_for(state="visible", timeout=per_selector_timeout)
            if i > 0:
                logger.debug("Selector %s=%r matched (fallback #%d)", sel.by, sel.value, i + 1)
            return locator.first
        except Exception:
            logger.debug("Selector %s=%r missed, trying next...", sel.by, sel.value)
            continue

    raise AllSelectorsFailedError(target.selectors, timeout_ms)


async def find_element_soft(
    page: Page,
    target: SelectorTarget,
    timeout_ms: int = 2000,
) -> Locator | None:
    """Like find_element but returns None instead of raising."""
    try:
        return await find_element(page, target, timeout_ms)
    except (AllSelectorsFailedError, ValueError):
        return None
