"""Shared Playwright browser configuration helpers.

Standardizes viewport/full-screen behavior across all browser launches in
Amplifier so platform UI elements are never cut off.

Behavior:
- Headless mode: use a large viewport (1920x1080) since there's no window
  to maximize.
- Headed mode: use --start-maximized + no_viewport=True so the actual
  window opens maximized to the user's screen.

Usage:
    kwargs = dict(user_data_dir=..., headless=True, args=[...])
    apply_full_screen(kwargs, headless=True)
    context = await pw.chromium.launch_persistent_context(**kwargs)
"""

# Large headless viewport — covers virtually all desktop platform UIs
HEADLESS_VIEWPORT = {"width": 1920, "height": 1080}
MAXIMIZE_ARG = "--start-maximized"


def apply_full_screen(kwargs: dict, headless: bool) -> dict:
    """Mutate launch_persistent_context kwargs to enable full-screen browser.

    Args:
        kwargs: The kwargs dict that will be passed to launch_persistent_context.
            Modified in-place.
        headless: Whether the browser will be launched in headless mode.

    Returns:
        The same kwargs dict (for chaining).
    """
    if headless:
        # Headless: set a large viewport. no_viewport not applicable here.
        kwargs["viewport"] = HEADLESS_VIEWPORT
        kwargs.pop("no_viewport", None)
    else:
        # Headed: --start-maximized + no_viewport=True opens the actual
        # browser window maximized to the user's screen size.
        kwargs["no_viewport"] = True
        kwargs.pop("viewport", None)
        existing_args = list(kwargs.get("args") or [])
        if MAXIMIZE_ARG not in existing_args:
            existing_args.append(MAXIMIZE_ARG)
        kwargs["args"] = existing_args
    return kwargs
