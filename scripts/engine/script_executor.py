"""Declarative script executor — drives Playwright from JSON posting scripts.

Reads a PlatformScript, iterates steps, dispatches to action handlers.
Uses SelectorChain for resilient element finding, HumanTiming for anti-detection,
and ErrorRecovery for graceful failure handling.

Inspired by AmpliFire v3's ScriptExecutor.kt.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from engine import error_recovery, human_timing, selector_chain
from engine.script_parser import (
    DelayRange,
    PlatformScript,
    ScriptStep,
    SelectorTarget,
    WaitCondition,
    resolve_variables,
)

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    success: bool
    step_id: str
    message: str = ""


@dataclass
class ExecutionResult:
    success: bool
    platform: str = ""
    action: str = ""
    failed_step: str | None = None
    error: str | None = None
    log: list[StepResult] = field(default_factory=list)
    post_url: str | None = None


class ScriptExecutor:
    """Execute a declarative posting script against a Playwright page."""

    def __init__(self, page: Page, variables: dict[str, str] | None = None):
        self.page = page
        self.variables = variables or {}
        self._log: list[StepResult] = []
        # Collected during execution (scripts can set these)
        self.post_url: str | None = None

    async def execute(self, script: PlatformScript) -> ExecutionResult:
        """Run all steps in a script. Returns ExecutionResult."""
        self._log = []
        self.post_url = None

        for step in script.steps:
            result = await self._run_step_with_recovery(step, script)
            self._log.append(result)
            if not result.success:
                if step.optional:
                    logger.warning(
                        "Optional step %s failed (%s), continuing",
                        step.id, result.message,
                    )
                    continue
                return ExecutionResult(
                    success=False,
                    platform=script.platform,
                    action=script.action,
                    failed_step=step.id,
                    error=result.message,
                    log=self._log,
                    post_url=self.post_url,
                )

        return ExecutionResult(
            success=True,
            platform=script.platform,
            action=script.action,
            log=self._log,
            post_url=self.post_url,
        )

    async def _run_step_with_recovery(
        self, step: ScriptStep, script: PlatformScript
    ) -> StepResult:
        """Execute a step with error recovery and retries."""
        for attempt in range(script.error_recovery.max_retries + 1):
            result = await self._execute_step(step)
            if result.success:
                return result

            # Determine error type from the failure message
            error_type = self._classify_error(result.message)

            # Ask recovery handler what to do
            recovery = await error_recovery.handle_error(
                self.page, step, error_type, attempt, script.error_recovery
            )

            if not recovery.should_retry:
                return result

            if recovery.wait_seconds > 0:
                await asyncio.sleep(recovery.wait_seconds)

        return StepResult(success=False, step_id=step.id, message="Max retries exhausted")

    async def _execute_step(self, step: ScriptStep) -> StepResult:
        """Dispatch a single step to the appropriate handler."""
        try:
            # Pre-step delay
            await human_timing.random_delay(step.delay_before_ms)

            # Dispatch by type
            handler = self._get_handler(step.type)
            if handler is None:
                return StepResult(False, step.id, f"Unknown step type: {step.type}")

            await handler(step)

            # Post-step delay
            await human_timing.random_delay(step.delay_after_ms)

            # Wait for expected condition
            if step.wait_for:
                await self._wait_for_condition(step.wait_for)

            # Screenshot if requested
            if step.screenshot:
                await self._take_screenshot(step.id)

            desc = step.description or step.type
            return StepResult(True, step.id, desc)

        except selector_chain.AllSelectorsFailedError as e:
            return StepResult(False, step.id, f"element_not_found: {e}")
        except asyncio.TimeoutError:
            return StepResult(False, step.id, f"timeout on step {step.id}")
        except Exception as e:
            return StepResult(False, step.id, f"error: {e}")

    def _get_handler(self, step_type: str):
        """Map step type string to handler method."""
        return {
            "goto": self._handle_goto,
            "click": self._handle_click,
            "text_input": self._handle_text_input,
            "file_upload": self._handle_file_upload,
            "keyboard": self._handle_keyboard,
            "dispatch_event": self._handle_dispatch_event,
            "wait_and_verify": self._handle_wait_and_verify,
            "scroll": self._handle_scroll,
            "evaluate": self._handle_evaluate,
            "wait": self._handle_wait,
            "screenshot": self._handle_screenshot,
            "extract_url": self._handle_extract_url,
            "browse_feed": self._handle_browse_feed,
        }.get(step_type)

    # ── Action Handlers ──────────────────────────────────────────────────

    async def _handle_goto(self, step: ScriptStep) -> None:
        url = self._resolve(step.url or "")
        logger.info("Step %s: navigating to %s", step.id, url)
        await self.page.goto(url, timeout=step.timeout_ms or 30000, wait_until="domcontentloaded")

    async def _handle_click(self, step: ScriptStep) -> None:
        locator = await selector_chain.find_element(
            self.page, step.target, timeout_ms=step.timeout_ms or 5000
        )
        logger.info("Step %s: clicking element", step.id)
        await locator.click(force=step.force, click_count=step.click_count)

    async def _handle_text_input(self, step: ScriptStep) -> None:
        text = self._resolve(step.text or "")
        if not text.strip():
            logger.info("Step %s: text is empty, skipping", step.id)
            return

        if step.target:
            locator = await selector_chain.find_element(
                self.page, step.target, timeout_ms=step.timeout_ms or 5000
            )
            logger.info("Step %s: typing %d chars", step.id, len(text))
            await human_timing.type_text_in_locator(
                self.page, locator, text, step.typing_speed
            )
        else:
            # No target — type via keyboard (for shadow DOM where element is pre-focused)
            delay_ms = 30
            if step.typing_speed:
                delay_ms = (step.typing_speed.min + step.typing_speed.max) // 2
            logger.info("Step %s: typing %d chars via keyboard", step.id, len(text))
            await self.page.keyboard.type(text, delay=delay_ms)

    async def _handle_file_upload(self, step: ScriptStep) -> None:
        file_path = self._resolve(step.file_path or "")
        if not file_path or not Path(file_path).exists():
            logger.info("Step %s: no file at %s, skipping", step.id, file_path)
            return

        abs_path = str(Path(file_path).resolve())

        # Method 1: Direct set_input_files on a file input selector
        if step.file_selector:
            sel = self._resolve(step.file_selector)
            fi = self.page.locator(sel).first
            await fi.set_input_files(abs_path)
            logger.info("Step %s: uploaded via file input %s", step.id, sel)
            return

        # Method 2: Use target selector to find the file input
        if step.target:
            locator = await selector_chain.find_element(
                self.page, step.target, timeout_ms=step.timeout_ms or 5000
            )
            await locator.set_input_files(abs_path)
            logger.info("Step %s: uploaded via target selector", step.id)
            return

        logger.warning("Step %s: no file_selector or target — can't upload", step.id)

    async def _handle_keyboard(self, step: ScriptStep) -> None:
        key = self._resolve(step.key or "")
        logger.info("Step %s: pressing %s", step.id, key)
        await self.page.keyboard.press(key)

    async def _handle_dispatch_event(self, step: ScriptStep) -> None:
        """Dispatch a DOM event on an element (for cases where .click() is intercepted)."""
        locator = await selector_chain.find_element(
            self.page, step.target, timeout_ms=step.timeout_ms or 5000
        )
        event_name = self._resolve(step.text or "click")
        logger.info("Step %s: dispatching '%s' event", step.id, event_name)
        await locator.dispatch_event(event_name)

    async def _handle_wait_and_verify(self, step: ScriptStep) -> None:
        """Wait for one of the success signals to appear."""
        if not step.success_signals:
            return

        timeout = step.timeout_ms or 10000
        deadline = asyncio.get_event_loop().time() + (timeout / 1000)

        while asyncio.get_event_loop().time() < deadline:
            for signal in step.success_signals:
                try:
                    if signal.text:
                        loc = self.page.get_by_text(signal.text).first
                        if await loc.is_visible(timeout=500):
                            logger.info("Step %s: verified — found text '%s'", step.id, signal.text)
                            return
                    if signal.selector:
                        loc = self.page.locator(signal.selector).first
                        if await loc.is_visible(timeout=500):
                            logger.info("Step %s: verified — found selector '%s'", step.id, signal.selector)
                            return
                except Exception:
                    pass
            await asyncio.sleep(1.0)

        logger.warning("Step %s: verification timed out after %dms", step.id, timeout)
        # Don't raise — verification timeout is a warning, not necessarily a failure.
        # The post may have succeeded but the success signal wasn't detected.

    async def _handle_scroll(self, step: ScriptStep) -> None:
        amount = step.timeout_ms or 300  # Reuse timeout_ms as scroll amount
        await self.page.mouse.wheel(0, amount)
        logger.info("Step %s: scrolled %dpx", step.id, amount)

    async def _handle_evaluate(self, step: ScriptStep) -> None:
        """Run JavaScript on the page or a target element."""
        js = self._resolve(step.js_code or "")
        if not js:
            return

        # Resolve JS args from variables
        args = []
        if step.js_args:
            args = [self._resolve(f"{{{{{a}}}}}") for a in step.js_args]

        if step.target:
            locator = await selector_chain.find_element(
                self.page, step.target, timeout_ms=step.timeout_ms or 5000
            )
            if args:
                result = await locator.evaluate(js, args[0] if len(args) == 1 else args)
            else:
                result = await locator.evaluate(js)
        else:
            if args:
                result = await self.page.evaluate(js, args[0] if len(args) == 1 else args)
            else:
                result = await self.page.evaluate(js)

        logger.info("Step %s: JS result = %s", step.id, str(result)[:200])
        # Store result as a variable for later steps
        if isinstance(result, str):
            self.variables[f"_result_{step.id}"] = result

    async def _handle_wait(self, step: ScriptStep) -> None:
        ms = step.timeout_ms or 1000
        await asyncio.sleep(ms / 1000)

    async def _handle_screenshot(self, step: ScriptStep) -> None:
        await self._take_screenshot(step.id)

    async def _handle_extract_url(self, step: ScriptStep) -> None:
        """Extract a URL from an element or the page and store it as post_url."""
        if step.target:
            locator = await selector_chain.find_element_soft(
                self.page, step.target, timeout_ms=step.timeout_ms or 5000
            )
            if locator:
                href = await locator.get_attribute("href")
                if href:
                    if href.startswith("http"):
                        url = href
                    elif href.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(self.page.url)
                        url = f"{parsed.scheme}://{parsed.netloc}{href}"
                    else:
                        url = f"https://{href}"
                    self.post_url = url
                    self.variables["post_url"] = url
                    logger.info("Step %s: extracted URL %s", step.id, url)
                    return

        # Fallback: use current page URL only if no URL was captured yet
        if not self.post_url:
            self.post_url = self.page.url
            self.variables["post_url"] = self.page.url
            logger.info("Step %s: using page URL %s", step.id, self.page.url)
        else:
            logger.info("Step %s: keeping previously captured URL %s", step.id, self.post_url)

    async def _handle_browse_feed(self, step: ScriptStep) -> None:
        """Simulate brief feed browsing."""
        duration = step.timeout_ms or None
        await human_timing.browse_feed(self.page, duration)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve(self, text: str) -> str:
        """Resolve {{variable}} placeholders."""
        return resolve_variables(text, self.variables)

    async def _wait_for_condition(self, condition: WaitCondition) -> None:
        """Wait for a WaitCondition to be satisfied."""
        timeout = condition.timeout_ms

        if condition.selector:
            await self.page.locator(condition.selector).first.wait_for(
                state="visible", timeout=timeout
            )
        elif condition.text:
            await self.page.get_by_text(condition.text).first.wait_for(
                state="visible", timeout=timeout
            )
        elif condition.id:
            await self.page.locator(f"#{condition.id}").first.wait_for(
                state="visible", timeout=timeout
            )

    async def _take_screenshot(self, step_id: str) -> None:
        try:
            from pathlib import Path
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            path = log_dir / f"script_{step_id}.png"
            await self.page.screenshot(path=str(path))
            logger.info("Screenshot saved: %s", path)
        except Exception as e:
            logger.warning("Failed to take screenshot: %s", e)

    @staticmethod
    def _classify_error(message: str) -> str:
        """Classify an error message into a recovery-actionable type."""
        msg = message.lower()
        if "element_not_found" in msg or "all selectors failed" in msg:
            return "element_not_found"
        if "timeout" in msg:
            return "timeout"
        if "popup" in msg or "dialog" in msg:
            return "popup"
        if "navigation" in msg or "unexpected" in msg:
            return "unexpected_screen"
        return "unknown"
