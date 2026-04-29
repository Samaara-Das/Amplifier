"""CSRF protection for FastAPI HTML form routes.

Uses the double-submit cookie pattern:
1. Middleware sets a csrf_token cookie on every GET response (random, readable by JS)
2. JavaScript reads the cookie and injects a hidden input into all POST forms
3. On POST, middleware checks the form field matches the cookie

Only applies to form-submitted POST requests (Content-Type: form-urlencoded).
API routes using JSON + Bearer tokens are exempt.
"""

import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

# Routes exempt from CSRF (API routes use JWT, not cookies)
_EXEMPT_PREFIXES = (b"/api/", b"/health", b"/docs", b"/openapi.json", b"/redoc")

COOKIE_NAME = "csrf_token"
FORM_FIELD = "csrf_token"


class CSRFMiddleware:
    """Pure ASGI middleware — doesn't consume the request body."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").encode()
        method = scope.get("method", "GET")

        # Skip exempt routes
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Parse cookies from headers
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode()
        cookies = {}
        if cookie_header:
            for part in cookie_header.split("; "):
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()

        cookie_token = cookies.get(COOKIE_NAME)

        # On form POST: validate CSRF token
        if method == "POST":
            ct = headers.get(b"content-type", b"").decode()
            # Only intercept urlencoded form bodies. multipart uploads contain
            # binary file content that is NOT utf-8 decodable, so trying to
            # parse_qs() the body crashes with UnicodeDecodeError. Multipart
            # POST endpoints (e.g. /company/campaigns/upload-asset) handle
            # CSRF separately via a header or cookie check inside the route.
            if "application/x-www-form-urlencoded" in ct:
                if not cookie_token:
                    await self._send_redirect(send, scope)
                    return

                # Buffer the body to read form data without consuming it
                body = b""
                while True:
                    message = await receive()
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break

                # Parse form field
                form_data = parse_qs(body.decode())
                form_token = form_data.get(FORM_FIELD, [None])[0]

                if not form_token or form_token != cookie_token:
                    await self._send_redirect(send, scope)
                    return

                # Re-create receive so the route handler can read the body
                body_sent = False
                async def cached_receive():
                    nonlocal body_sent
                    if not body_sent:
                        body_sent = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return {"type": "http.request", "body": b"", "more_body": False}

                # Set CSRF cookie on response if needed
                if not cookie_token:
                    send = self._wrap_send_with_cookie(send)

                await self.app(scope, cached_receive, send)
                return

        # For non-POST: set CSRF cookie if missing
        if not cookie_token:
            send = self._wrap_send_with_cookie(send)

        await self.app(scope, receive, send)

    def _wrap_send_with_cookie(self, send):
        """Wrap the send callable to inject a Set-Cookie header."""
        token = secrets.token_hex(32)
        cookie_value = f"{COOKIE_NAME}={token}; Path=/; SameSite=Lax; Max-Age=86400"

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie_value.encode()))
                message = {**message, "headers": headers}
            await send(message)

        return wrapped_send

    async def _send_redirect(self, send, scope):
        """Send a 302 redirect back to the referer or the current page."""
        headers = dict(scope.get("headers", []))
        referer = headers.get(b"referer", scope.get("path", "/").encode()).decode()
        await send({
            "type": "http.response.start",
            "status": 302,
            "headers": [
                (b"location", referer.encode()),
                (b"content-length", b"0"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"",
        })
