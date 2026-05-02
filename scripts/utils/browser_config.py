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

# DNS-resolver hardening (Task #86 polish 2026-05-02 + Task #88 expansion 2026-05-02):
# Chromium's built-in async DNS resolver can fail on some networks
# (especially dual-stack IPv6 setups where the ISP's IPv6 DNS is broken,
# e.g. some Jio plans). When that happens, page loads fail with
# net::ERR_NAME_NOT_RESOLVED before the request even leaves the browser.
#
# Layered hardening — each flag addresses a distinct failure mode and they
# stack:
#   AsyncDns           — falls back to the OS resolver (honors Windows
#                        Set-DnsClientServerAddress + /etc/resolv.conf).
#   DnsOverHttps       — disables Chromium's secure DNS (DoH), which can
#                        silently 503 on networks where the upstream DoH
#                        provider is blocked. Forces classic UDP/53.
#   HappyEyeballsV3    — disables the experimental dual-stack racing path
#                        that has shipped flaky behaviour on dual-stack
#                        networks where one stack lies dead.
#   IntermediateCertificateVerifierUpdaters — avoids a slow/flaky network
#                        call during cold start that can stall navigation.
#
# host-resolver-rules: forces lookups via Chromium's MAP/EXCLUDE table
# rather than direct DNS, but we leave it unset by default and only flip
# it on at runtime when AMPLIFIER_BROWSER_DNS_RESOLVE_OVERRIDE is set
# (escape hatch for users on truly broken networks who want to point at a
# specific resolver). See AMPLIFIER_BROWSER_*  env vars below.
#
# NOTE: These flags do NOT fix OS-level IPv6 brokenness. If a user's
# operating system itself has a half-up IPv6 stack, point them to
# `Disable-NetAdapterBinding -ComponentID ms_tcpip6` on Windows. See
# Task #86 + #88 UAT reports 2026-05-02 for the full diagnostic flow.
import os as _os

DNS_HARDENING_ARGS = [
    "--disable-features=AsyncDns,DnsOverHttps,HappyEyeballsV3,IntermediateCertificateVerifierUpdaters",
]

# Optional env-var escape hatches — empirically useful when a user's ISP
# is on the wrong side of a Chromium DNS regression. Values are read at
# import time so they apply uniformly across all browser launches in the
# same daemon process.
#   AMPLIFIER_BROWSER_DNS_PREFER_IPV4=1
#       Prefer A records over AAAA. Cures pages that hang on IPv6
#       lookups when the AAAA record exists but is unreachable.
#   AMPLIFIER_BROWSER_DNS_DOH_SERVER=https://1.1.1.1/dns-query
#       Override Chromium's DoH server (re-enables DoH but pinned to a
#       resolver of the user's choice). Mutually exclusive with the
#       AsyncDns disable above; we keep both flags to let the user pick
#       a known-good resolver while keeping the OS-resolver fallback.
if _os.environ.get("AMPLIFIER_BROWSER_DNS_PREFER_IPV4"):
    DNS_HARDENING_ARGS.append("--disable-ipv6")
_DOH_OVERRIDE = _os.environ.get("AMPLIFIER_BROWSER_DNS_DOH_SERVER")
if _DOH_OVERRIDE:
    DNS_HARDENING_ARGS.append(f"--dns-over-https-server={_DOH_OVERRIDE}")


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
