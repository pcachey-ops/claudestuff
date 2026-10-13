"""Create a digital-download listing on Etsy via Open API v3.

Listings are created as drafts. Etsy charges its $0.20 listing fee only when a listing is
activated, so drafts cost nothing until you (or --activate) publish them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import requests

from ..models import ProductSpec

API = "https://openapi.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

AI_DISCLOSURE = (
    "\n\nAbout this design: created by our shop using AI-assisted tools, then laid out and "
    "reviewed by us."
)


class EtsyError(RuntimeError):
    pass


@dataclass
class EtsyConfig:
    keystring: str
    shared_secret: str
    refresh_token: str
    shop_id: str
    taxonomy_id: int

    @classmethod
    def from_env(cls) -> "EtsyConfig | None":
        names = ["ETSY_KEYSTRING", "ETSY_SHARED_SECRET", "ETSY_REFRESH_TOKEN", "ETSY_SHOP_ID", "ETSY_TAXONOMY_ID"]
        values = [os.getenv(n) for n in names]
        if not all(values):
            return None
        k, s, r, shop, tax = values
        return cls(k, s, r, shop, int(tax))

    @property
    def api_key_header(self) -> str:
        return f"{self.keystring}:{self.shared_secret}"


class EtsyPublisher:
    def __init__(self, config: EtsyConfig, session: requests.Session | None = None):
        self.config = config
        self.http = session or requests.Session()
        self.new_refresh_token: str | None = None
        self.http.headers.update({"x-api-key": config.api_key_header})

    def _authenticate(self) -> None:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": self.config.keystring,
            "refresh_token": self.config.refresh_token,
        }, timeout=30)
        if r.status_code != 200:
            raise EtsyError(f"Token refresh failed ({r.status_code}): {r.text[:300]}. "
                            "Re-run scripts/etsy_auth.py to mint a new refresh token.")
        tokens = r.json()
        self.http.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        self.new_refresh_token = tokens.get("refresh_token")

    def _call(self, method: str, path: str, **kwargs) -> dict:
        r = self.http.request(method, f"{API}{path}", timeout=120, **kwargs)
        if r.status_code >= 300:
            raise EtsyError(f"{method} {path} failed ({r.status_code}): {r.text[:500]}")
        return r.json()

    def publish(self, spec: ProductSpec, pdf: Path, cover: Path, activate: bool = False) -> dict:
        self._authenticate()
        shop = self.config.shop_id

        listing = self._call("POST", f"/shops/{shop}/listings", data={
            "quantity": 999,
            "title": spec.title,
            "description": spec.description + AI_DISCLOSURE,
            "price": f"{spec.price_usd:.2f}",
            "who_made": "i_did",
            "when_made": "made_to_order",
            "taxonomy_id": self.config.taxonomy_id,
            "type": "download",
            "is_supply": "false",
            "tags": ",".join(spec.tags),
        })
        listing_id = listing["listing_id"]

        with cover.open("rb") as fh:
            self._call("POST", f"/shops/{shop}/listings/{listing_id}/images",
                       files={"image": (cover.name, fh, "image/png")}, data={"rank": 1})
        with pdf.open("rb") as fh:
            self._call("POST", f"/shops/{shop}/listings/{listing_id}/files",
                       files={"file": (pdf.name, fh, "application/pdf")}, data={"name": pdf.name, "rank": 1})

        if activate:
            self._call("PATCH", f"/shops/{shop}/listings/{listing_id}", data={"state": "active"})

        return {"listing_id": listing_id, "url": f"https://www.etsy.com/listing/{listing_id}",
                "state": "active" if activate else "draft"}
