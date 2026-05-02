# Task #88 — Chromium DNS Robustness (Patchright Launch Args)

**Status:** pending
**Branch:** flask-user-app
**Discovered:** during /uat-task 86, 2026-05-02 — Jio ISP IPv6 DNS resolution failures

## What this fixes

Some user networks (notably some Jio ISP plans on India dual-stack IPv6) deliver broken or extremely slow DNS responses to Chromium's built-in `AsyncDns` resolver. When that happens, Patchright sessions fail at navigation with `net::ERR_NAME_NOT_RESOLVED` BEFORE the daemon can reach LinkedIn / Facebook / Reddit — leaving the user unable to scrape their own profile, unable to post, and seeing only "Profile scrape returned no data" with no actionable error.

Task #86 added the first hardening flag (`--disable-features=AsyncDns`) and noted in code that "this flag alone is sometimes insufficient". Task #88 layers on additional resolver hardening + env-var escape hatches so the same fresh-laptop UAT works on flaky home networks too.

## Files changed

| File | Change |
|---|---|
| `scripts/utils/browser_config.py` | Extend `DNS_HARDENING_ARGS` with `DnsOverHttps`, `HappyEyeballsV3`, `IntermediateCertificateVerifierUpdaters` disables; add env-var-driven flag injection for `AMPLIFIER_BROWSER_DNS_PREFER_IPV4` (→ `--disable-ipv6`) and `AMPLIFIER_BROWSER_DNS_DOH_SERVER` (→ `--dns-over-https-server=…`). |

## Features to verify end-to-end (Task #88)

1. Default `DNS_HARDENING_ARGS` includes the four documented flag families (AsyncDns, DnsOverHttps, HappyEyeballsV3, IntermediateCertificateVerifierUpdaters) — AC1
2. `apply_full_screen()` injects all default DNS hardening args into the `kwargs["args"]` list, idempotently — AC2
3. Setting `AMPLIFIER_BROWSER_DNS_PREFER_IPV4=1` adds `--disable-ipv6` to the launch args — AC3
4. Setting `AMPLIFIER_BROWSER_DNS_DOH_SERVER=https://1.1.1.1/dns-query` adds `--dns-over-https-server=https://1.1.1.1/dns-query` to the launch args — AC4
5. The default flags do not break the existing pytest suite (`tests/server/`) — AC5
6. A real Patchright browser launch with the hardening args succeeds (no Chromium startup error from any flag) — AC6

## Verification Procedure — Task #88

### Preconditions

- Local checkout on `flask-user-app` branch with the patched `browser_config.py`.
- Patchright installed: `python -c "from patchright.async_api import async_playwright; print('ok')"` → `ok`.
- Chromium binary installed: `python -m patchright install chromium` succeeded previously (binary lives under `~/AppData/Local/ms-playwright/chromium-*`).

### Test data setup

None — the AC checks are pure import + launch.

### Test-mode flags

| Flag | Effect | Used by AC |
|------|--------|-----------|
| `AMPLIFIER_BROWSER_DNS_PREFER_IPV4=1` | adds `--disable-ipv6` | AC3 |
| `AMPLIFIER_BROWSER_DNS_DOH_SERVER=<url>` | adds `--dns-over-https-server=<url>` | AC4 |

---

### AC1 — Default `DNS_HARDENING_ARGS` covers all 4 flag families — PASS criterion

| Field | Value |
|-------|-------|
| **Setup** | Fresh interpreter (no env vars set). |
| **Action** | `python -c "from scripts.utils.browser_config import DNS_HARDENING_ARGS; print(DNS_HARDENING_ARGS)"` |
| **Expected** | The list contains exactly one combined `--disable-features=…` arg whose value (split on `,`) is the set `{AsyncDns, DnsOverHttps, HappyEyeballsV3, IntermediateCertificateVerifierUpdaters}`. |
| **Automated** | yes |
| **Automation** | python one-liner above + assert |
| **Evidence** | stdout dump showing the args |
| **Cleanup** | none |

### AC2 — `apply_full_screen()` injects default args idempotently

| Field | Value |
|-------|-------|
| **Setup** | empty kwargs dict |
| **Action** | call `apply_full_screen(kwargs={}, headless=True)` twice in succession |
| **Expected** | After the first call, `kwargs["args"]` contains the `--disable-features=…` flag. After the second call, the flag count is unchanged (no duplicates). |
| **Automated** | yes |
| **Automation** | python one-liner |
| **Evidence** | before/after `kwargs["args"]` dump showing flag count = 1 |
| **Cleanup** | none |

### AC3 — `AMPLIFIER_BROWSER_DNS_PREFER_IPV4=1` adds `--disable-ipv6`

| Field | Value |
|-------|-------|
| **Setup** | unset env, then set `AMPLIFIER_BROWSER_DNS_PREFER_IPV4=1` |
| **Action** | `import importlib, os; os.environ['AMPLIFIER_BROWSER_DNS_PREFER_IPV4']='1'; from scripts.utils import browser_config as bc; importlib.reload(bc); print(bc.DNS_HARDENING_ARGS)` |
| **Expected** | The args list contains `--disable-ipv6` AS A SECOND ELEMENT (after the combined `--disable-features=…` flag). |
| **Automated** | yes |
| **Automation** | python script with importlib reload |
| **Evidence** | stdout showing both flags |
| **Cleanup** | unset env var |

### AC4 — `AMPLIFIER_BROWSER_DNS_DOH_SERVER` adds DoH override

| Field | Value |
|-------|-------|
| **Setup** | set `AMPLIFIER_BROWSER_DNS_DOH_SERVER=https://1.1.1.1/dns-query` |
| **Action** | `importlib.reload(bc)` then inspect `bc.DNS_HARDENING_ARGS` |
| **Expected** | The args list contains `--dns-over-https-server=https://1.1.1.1/dns-query`. |
| **Automated** | yes |
| **Automation** | python script with importlib reload |
| **Evidence** | stdout showing the DoH flag |
| **Cleanup** | unset env var |

### AC5 — Existing pytest suite unaffected

| Field | Value |
|-------|-------|
| **Setup** | clean checkout |
| **Action** | `python -m pytest tests/ -q -x --timeout=120` |
| **Expected** | All tests still pass (336 baseline as of 2026-05-02). No new failures. No new warnings about the flags. |
| **Automated** | yes |
| **Automation** | pytest |
| **Evidence** | pytest summary line |
| **Cleanup** | none |

### AC6 — Real Patchright launch succeeds with hardening args

| Field | Value |
|-------|-------|
| **Setup** | env vars unset; Patchright + Chromium installed |
| **Action** | run `scripts/uat/probe_dns_hardening.py` (created during this UAT — minimal Patchright launcher that uses `apply_full_screen()` and visits `about:blank` then closes). |
| **Expected** | Browser launches and closes cleanly within 30s. No Chromium startup errors, no flag-rejection warnings on stderr. Exit code 0. |
| **Automated** | yes |
| **Automation** | `python scripts/uat/probe_dns_hardening.py` |
| **Evidence** | script stdout + exit code |
| **Cleanup** | browser process exits naturally |

---

### Aggregated PASS rule for Task #88

Task #88 is marked done in task-master ONLY when:

1. AC1–AC6 all PASS
2. No new pytest failures introduced
3. UAT report `docs/uat/reports/task-88-<yyyy-mm-dd>-<hhmm>.md` written

---

### Optional manual smoke (NOT required for marking done)

On a fresh laptop or VM with broken IPv6 DNS, manually run `python scripts/login_setup.py linkedin` and confirm the browser still navigates to `linkedin.com` rather than failing with `ERR_NAME_NOT_RESOLVED`. This is environment-dependent and not part of the autonomous UAT — captured here as a regression-test recipe for the maintainer.
