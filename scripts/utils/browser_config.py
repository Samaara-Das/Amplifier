"""Shared Playwright browser configuration helpers.

Standardizes viewport/full-screen behavior + DNS-resolver hardening across
all browser launches in Amplifier.

Behavior:
- Headless mode: use a large viewport (1920x1080) since there's no window
  to maximize.
- Headed mode: use --start-maximized + no_viewport=True so the actual
  window opens maximized to the user's screen.
- DNS hardening: disable Chromium's built-in async DNS resolver (which
  prefers IPv6 and bypasses system DNS). Falls back to system resolver
  so users with flaky ISP IPv6 DNS still get successful page loads.

Usage:
    kwargs = dict(user_data_dir=..., headless=True, args=[...])
    apply_full_screen(kwargs, headless=True)
    context = await pw.chromium.launch_persistent_context(**kwargs)
"""

# Large headless viewport — covers virtually all desktop platform UIs
HEADLESS_VIEWPORT = {"width": 1920, "height": 1080}
MAXIMIZE_ARG = "--start-maximized"

# DNS-resolver hardening (Task #86 polish, 2026-05-02):
# Chromium's built-in async DNS resolver can fail on some networks
# (especially dual-stack IPv6 setups where the ISP's IPv6 DNS is broken).
# When that happens, page loads fail with net::ERR_NAME_NOT_RESOLVED.
# This flag tells Chromium to fall back to the OS resolver, which honors
# Set-DnsClientServerAddress on Windows and /etc/resolv.conf elsewhere.
# NOTE: Empirically this flag alone is sometimes insufficient — users
# with broken ISP IPv6 may also need to disable IPv6 at the OS level
# (`Disable-NetAdapterBinding -ComponentID ms_tcpip6` on Windows). See
# Task #86 UAT report 2026-05-02 for details.
DNS_HARDENING_ARGS = [
    "--disable-features=AsyncDns",
]


def apply_full_screen(kwargs: dict, headless: bool) -> dict:
    """Mutate launch_persistent_context kwargs to enable full-screen browser.

    Also applies DNS-hardening args (idempotent — safe to call twice).

    Args:
        kwargs: The kwargs dict that will be passed to launch_persistent_context.
            Modified in-place.
        headless: Whether the browser will be launched in headless mode.

    Returns:
        The same kwargs dict (for chaining).
    """
    # DNS hardening always applied
    existing_args = list(kwargs.get("args") or [])
    for arg in DNS_HARDENING_ARGS:
        if arg not in existing_args:
            existing_args.append(arg)
    kwargs["args"] = existing_args

    if headless:
        # Headless: set a large viewport. no_viewport not applicable here.
        kwargs["viewport"] = HEADLESS_VIEWPORT
        kwargs.pop("no_viewport", None)
    else:
        # Headed: --start-maximized + no_viewport=True opens the actual
        # browser window maximized to the user's screen size.
        kwargs["no_viewport"] = True
        kwargs.pop("viewport", None)
        if MAXIMIZE_ARG not in kwargs["args"]:
            kwargs["args"].append(MAXIMIZE_ARG)
    return kwargs
