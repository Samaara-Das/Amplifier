"""Parse declarative JSON posting scripts into executable data models.

Each platform's posting flow is defined in a JSON file (e.g., config/scripts/x_post.json)
with steps, selectors, timing, and error recovery — not hardcoded Python.

Inspired by AmpliFire v3's ScriptModel.kt + ScriptParser.kt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DelayRange:
    min: int = 0   # milliseconds
    max: int = 0

    @classmethod
    def from_raw(cls, raw) -> DelayRange | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return cls(min=raw.get("min", 0), max=raw.get("max", 0))
        if isinstance(raw, (int, float)):
            return cls(min=int(raw), max=int(raw))
        return None


@dataclass
class Selector:
    by: str        # css | text | role | testid | aria_label | xpath
    value: str

    @classmethod
    def from_raw(cls, raw: dict) -> Selector:
        return cls(by=raw["by"], value=raw["value"])


@dataclass
class SelectorTarget:
    strategy: str = "single"       # single | fallback_chain
    selectors: list[Selector] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict | None) -> SelectorTarget | None:
        if raw is None:
            return None
        strategy = raw.get("strategy", "single")
        selectors = []
        if "selectors" in raw:
            selectors = [Selector.from_raw(s) for s in raw["selectors"]]
        elif "by" in raw and "value" in raw:
            selectors = [Selector(by=raw["by"], value=raw["value"])]
        return cls(strategy=strategy, selectors=selectors)


@dataclass
class WaitCondition:
    selector: str | None = None
    text: str | None = None
    id: str | None = None
    content_desc: str | None = None
    timeout_ms: int = 10000

    @classmethod
    def from_raw(cls, raw: dict | None) -> WaitCondition | None:
        if raw is None:
            return None
        return cls(
            selector=raw.get("selector"),
            text=raw.get("text"),
            id=raw.get("id"),
            content_desc=raw.get("content_desc"),
            timeout_ms=raw.get("timeout_ms", 10000),
        )


@dataclass
class SuccessSignal:
    text: str | None = None
    selector: str | None = None
    id: str | None = None
    content_desc: str | None = None

    @classmethod
    def from_raw(cls, raw: dict) -> SuccessSignal:
        return cls(
            text=raw.get("text"),
            selector=raw.get("selector"),
            id=raw.get("id"),
            content_desc=raw.get("content_desc"),
        )


@dataclass
class ErrorRecoveryConfig:
    on_element_not_found: str = "retry_with_next_selector"
    on_unexpected_screen: str = "navigate_back_and_retry"
    on_popup: str = "dismiss_and_continue"
    on_timeout: str = "retry"
    max_retries: int = 3
    on_failure: str = "queue_for_manual"

    @classmethod
    def from_raw(cls, raw: dict | None) -> ErrorRecoveryConfig:
        if raw is None:
            return cls()
        return cls(
            on_element_not_found=raw.get("on_element_not_found", "retry_with_next_selector"),
            on_unexpected_screen=raw.get("on_unexpected_screen", "navigate_back_and_retry"),
            on_popup=raw.get("on_popup", "dismiss_and_continue"),
            on_timeout=raw.get("on_timeout", "retry"),
            max_retries=raw.get("max_retries", 3),
            on_failure=raw.get("on_failure", "queue_for_manual"),
        )


@dataclass
class ScriptStep:
    id: str
    type: str                              # goto, click, text_input, file_upload, keyboard,
                                           # dispatch_event, wait_and_verify, scroll, evaluate,
                                           # wait, screenshot
    # Target element
    target: SelectorTarget | None = None

    # Navigation
    url: str | None = None

    # Text input
    text: str | None = None
    typing_speed: DelayRange | None = None  # per-character delay

    # File upload
    file_path: str | None = None            # template variable like {{image_path}}
    file_selector: str | None = None        # CSS selector for the file input

    # Keyboard
    key: str | None = None                  # e.g. "Control+Enter", "Backspace"

    # JavaScript evaluation
    js_code: str | None = None
    js_args: list[str] | None = None        # template variables to pass as args

    # Timing
    delay_before_ms: DelayRange | None = None
    delay_after_ms: DelayRange | None = None

    # Waiting
    wait_for: WaitCondition | None = None
    timeout_ms: int | None = None

    # Verification
    success_signals: list[SuccessSignal] | None = None
    screenshot: bool = False

    # Click options
    force: bool = False
    click_count: int = 1

    # Misc
    description: str | None = None

    @classmethod
    def from_raw(cls, raw: dict) -> ScriptStep:
        return cls(
            id=raw["id"],
            type=raw["type"],
            target=SelectorTarget.from_raw(raw.get("target")),
            url=raw.get("url"),
            text=raw.get("text"),
            typing_speed=DelayRange.from_raw(raw.get("typing_speed")),
            file_path=raw.get("file_path") or raw.get("source"),
            file_selector=raw.get("file_selector"),
            key=raw.get("key"),
            js_code=raw.get("js_code"),
            js_args=raw.get("js_args"),
            delay_before_ms=DelayRange.from_raw(raw.get("delay_before_ms")),
            delay_after_ms=DelayRange.from_raw(raw.get("delay_after_ms")),
            wait_for=WaitCondition.from_raw(raw.get("wait_for")),
            timeout_ms=raw.get("timeout_ms"),
            success_signals=[SuccessSignal.from_raw(s) for s in raw["success_signals"]]
                if raw.get("success_signals") else None,
            screenshot=raw.get("screenshot", False),
            force=raw.get("force", False),
            click_count=raw.get("click_count", 1),
            description=raw.get("description"),
        )


@dataclass
class PlatformScript:
    platform: str
    action: str                            # post_text, post_with_image, post_text_and_image
    version: str
    home_url: str | None = None
    steps: list[ScriptStep] = field(default_factory=list)
    error_recovery: ErrorRecoveryConfig = field(default_factory=ErrorRecoveryConfig)
    variables_required: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict) -> PlatformScript:
        return cls(
            platform=raw["platform"],
            action=raw.get("action", "post"),
            version=raw.get("version", "0.0.0"),
            home_url=raw.get("home_url"),
            steps=[ScriptStep.from_raw(s) for s in raw.get("steps", [])],
            error_recovery=ErrorRecoveryConfig.from_raw(raw.get("error_recovery")),
            variables_required=raw.get("variables_required", []),
        )


# ── Parsing ──────────────────────────────────────────────────────────────────

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def resolve_variables(text: str, variables: dict[str, str]) -> str:
    """Replace {{var_name}} placeholders with actual values."""
    def _replace(match):
        key = match.group(1)
        return variables.get(key, match.group(0))  # keep original if not found
    return _VAR_PATTERN.sub(_replace, text)


def load_script(path: str | Path) -> PlatformScript:
    """Load and parse a JSON posting script from file."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PlatformScript.from_raw(raw)


def load_script_from_string(json_str: str) -> PlatformScript:
    """Parse a JSON posting script from a string."""
    raw = json.loads(json_str)
    return PlatformScript.from_raw(raw)
