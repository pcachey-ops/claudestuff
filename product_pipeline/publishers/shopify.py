"""Create a draft digital product in Shopify via the Admin GraphQL API."""

from __future__ import annotations

import html
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import requests

from ..models import ProductSpec


class ShopifyError(RuntimeError):
    pass


@dataclass
class ShopifyConfig:
    store: str  # e.g. "my-shop" or "my-shop.myshopify.com"
    token: str  # Admin API access token (shpat_...)
    api_version: str = "2026-07"

    @classmethod
    def from_env(cls) -> "ShopifyConfig | None":
        store, token = os.getenv("SHOPIFY_STORE"), os.getenv("SHOPIFY_ADMIN_TOKEN")
        if not (store and token):
            return None
        return cls(store, token, os.getenv("SHOPIFY_API_VERSION", "2026-07"))

    @property
    def endpoint(self) -> str:
        host = self.store if "." in self.store else f"{self.store}.myshopify.com"
        return f"https://{host}/admin/api/{self.api_version}/graphql.json"


class ShopifyPublisher:
    def __init__(self, config: ShopifyConfig, session: requests.Session | None = None):
        self.config = config
        self.http = session or requests.Session()
        self.http.headers.update({"X-Shopify-Access-Token": config.token, "Content-Type": "application/json"})

    def _gql(self, query: str, variables: dict) -> dict:
        r = self.http.post(self.config.endpoint, json={"query": query, "variables": variables}, timeout=60)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise ShopifyError(str(body["errors"]))
        data = body["data"]
        for result in data.values():
            if isinstance(result, dict) and result.get("userErrors"):
                raise ShopifyError(str(result["userErrors"]))
        return data

    def _staged_upload(self, path: Path, resource: str) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = self._gql(
            """mutation($input: [StagedUploadInput!]!) {
                 stagedUploadsCreate(input: $input) {
                   stagedTargets { url resourceUrl parameters { name value } }
                   userErrors { field message }
                 }
               }""",
            {"input": [{
                "filename": path.name, "mimeType": mime, "resource": resource,
                "httpMethod": "POST", "fileSize": str(path.stat().st_size),
            }]},
        )
        target = data["stagedUploadsCreate"]["stagedTargets"][0]
        form = {p["name"]: p["value"] for p in target["parameters"]}
        with path.open("rb") as fh:
            up = requests.post(target["url"], data=form, files={"file": (path.name, fh, mime)}, timeout=120)
        if up.status_code >= 300:
            raise ShopifyError(f"Staged upload failed ({up.status_code}): {up.text[:300]}")
        return target["resourceUrl"]

    def publish(self, spec: ProductSpec, pdf: Path, cover: Path, activate: bool = False) -> dict:
        cover_url = self._staged_upload(cover, "IMAGE")
        pdf_url = self._staged_upload(pdf, "FILE")

        files = self._gql(
            """mutation($files: [FileCreateInput!]!) {
                 fileCreate(files: $files) { files { id } userErrors { field message } }
               }""",
            {"files": [{"originalSource": pdf_url, "contentType": "FILE", "alt": spec.cover_title}]},
        )
        file_id = files["fileCreate"]["files"][0]["id"]

        description_html = "".join(f"<p>{html.escape(p)}</p>" for p in spec.description.split("\n") if p.strip())
        created = self._gql(
            """mutation($product: ProductCreateInput!, $media: [CreateMediaInput!]) {
                 productCreate(product: $product, media: $media) {
                   product { id handle variants(first: 1) { nodes { id } } }
                   userErrors { field message }
                 }
               }""",
            {
                "product": {
                    "title": spec.title,
                    "descriptionHtml": description_html,
                    "productType": "Digital Download",
                    "tags": spec.tags + ["digital-download", "auto-generated"],
                    "status": "ACTIVE" if activate else "DRAFT",
                    "metafields": [{
                        "namespace": "custom", "key": "download_file",
                        "type": "file_reference", "value": file_id,
                    }],
                },
                "media": [{"originalSource": cover_url, "mediaContentType": "IMAGE", "alt": spec.cover_title}],
            },
        )
        product = created["productCreate"]["product"]
        variant_id = product["variants"]["nodes"][0]["id"]

        self._gql(
            """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                 productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                   productVariants { id }
                   userErrors { field message }
                 }
               }""",
            {"productId": product["id"], "variants": [{
                "id": variant_id,
                "price": f"{spec.price_usd:.2f}",
                "inventoryPolicy": "CONTINUE",
                "inventoryItem": {"requiresShipping": False, "tracked": False},
            }]},
        )
        return {"product_id": product["id"], "handle": product["handle"], "file_id": file_id}
