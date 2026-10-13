"""One-time Etsy OAuth (PKCE) helper: prints a refresh token and your shop id.

Usage:
    ETSY_KEYSTRING=... ETSY_SHARED_SECRET=... python scripts/etsy_auth.py

Your Etsy app must list http://localhost:3003/callback as a redirect URI.
Refresh tokens last 90 days; re-run this before then and update the ETSY_REFRESH_TOKEN secret.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import os
import secrets
import urllib.parse
import webbrowser

import requests

REDIRECT = "http://localhost:3003/callback"
SCOPES = "listings_r listings_w shops_r"


def main() -> None:
    keystring = os.environ["ETSY_KEYSTRING"]
    secret = os.environ["ETSY_SHARED_SECRET"]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = "https://www.etsy.com/oauth/connect?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": keystring, "redirect_uri": REDIRECT, "scope": SCOPES,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })

    captured: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            captured.update(query)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Etsy authorised. You can close this tab.")

        def log_message(self, *args):
            pass

    print(f"Opening browser. If it doesn't open, visit:\n{url}\n")
    webbrowser.open(url)
    http.server.HTTPServer(("localhost", 3003), Handler).handle_request()

    if captured.get("state") != state or "code" not in captured:
        raise SystemExit(f"Authorisation failed: {captured}")

    tokens = requests.post("https://api.etsy.com/v3/public/oauth/token", data={
        "grant_type": "authorization_code", "client_id": keystring, "redirect_uri": REDIRECT,
        "code": captured["code"], "code_verifier": verifier,
    }, timeout=30).json()

    user_id = tokens["access_token"].split(".")[0]
    headers = {"x-api-key": f"{keystring}:{secret}", "Authorization": f"Bearer {tokens['access_token']}"}
    shop = requests.get(f"https://openapi.etsy.com/v3/application/users/{user_id}/shops",
                        headers=headers, timeout=30).json()

    print("Add these as secrets (GitHub repo → Settings → Secrets and variables → Actions):")
    print(f"  ETSY_REFRESH_TOKEN = {tokens['refresh_token']}")
    print(f"  ETSY_SHOP_ID       = {shop.get('shop_id')}")


if __name__ == "__main__":
    main()
