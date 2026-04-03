"""Structured error recovery with retry strategies for posting scripts.

Inspired by AmpliFire v3's error_recovery config in JSON scripts. Instead of
binary pass/fail, each script defines recovery strategies for different failure
types — catching ~30-40% of transient failures that currently kill posts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from engine.script_parser import ErrorRecoveryConfig, ScriptStep

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class StepError:
    """Details about a failed step for logging and debugging."""
    step_id: str
    error_type: str       # element_not_found | timeout | unexpected_screen | popup | unknown
    message: str
    attempt: int
    max_retries: int


@dataclass
class RecoveryResult:
    should_retry: bool = False
    wait_seconds: float = 0


async def _dismiss_popups(page: Page) -> bool:
    """Try to close common popup/modal patterns."""
    popup_selectors = [
        'button:has-text("Not now")',
        'button:has-text("Dismiss")',
        'button:has-text("Close")',
        'button:has-text("Maybe later")',
        'button:has-text("No thanks")',
        'button[aria-label="Close"]',
        'button[aria-label="Dismiss"]',
        '[role="dialog"] button:has-text("OK")',
        '[data-testid="confirmationSheetConfirm"]',
    ]
    for sel in popup_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click()
                logger.info("Dismissed popup via %s", sel)
                await asyncio.sleep(0.5)
                return True
        except Exception:
            continue
    return False


async def handle_error(
    page: Page,
    step: ScriptStep,
    error_type: str,
    attempt: int,
    config: ErrorRecoveryConfig,
) -> RecoveryResult:
    """Decide how to recover from a step failure.

    Returns RecoveryResult indicating whether to retry and how long to wait.
    """
    if attempt >= config.max_retries:
        logger.warning(
            "Step %s: max retries (%d) reached for %s — giving up",
            step.id, config.max_retries, error_type,
        )
        return RecoveryResult(should_retry=False)

    # Pick strategy based on error type
    if error_type == "element_not_found":
        strategy = config.on_element_not_found
    elif error_type == "unexpected_screen":
        strategy = config.on_unexpected_screen
    elif error_type == "popup":
        strategy = config.on_popup
    elif error_type == "timeout":
        strategy = config.on_timeout
    else:
        strategy = "retry"

    logger.info(
        "Step %s: error=%s attempt=%d/%d strategy=%s",
        step.id, error_type, attempt + 1, config.max_retries, strategy,
    )

    if strategy == "retry_with_next_selector":
        # Exponential backoff
        wait = 1.0 * (2 ** attempt)
        return RecoveryResult(should_retry=True, wait_seconds=wait)

    elif strategy == "navigate_back_and_retry":
        try:
            await page.go_back()
            await asyncio.sleep(2.0)
        except Exception:
            pass
        return RecoveryResult(should_retry=True, wait_seconds=1.0)

    elif strategy == "dismiss_and_continue":
        dismissed = await _dismiss_popups(page)
        if dismissed:
            return RecoveryResult(should_retry=True, wait_seconds=0.5)
        # No popup found — fall through to regular retry
        return RecoveryResult(should_retry=True, wait_seconds=1.0 * (2 ** attempt))

    elif strategy == "retry":
        wait = 1.0 * (2 ** attempt)
        return RecoveryResult(should_retry=True, wait_seconds=wait)

    elif strategy == "queue_for_manual":
        return RecoveryResult(should_retry=False)

    else:
        # Unknown strategy — retry with backoff
        return RecoveryResult(should_retry=True, wait_seconds=1.0 * (2 ** attempt))
