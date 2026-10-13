import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from product_pipeline import __main__ as cli
from product_pipeline.ledger import Ledger
from product_pipeline.models import Page, ProductSpec
from product_pipeline.publishers.shopify import ShopifyConfig, ShopifyPublisher
from product_pipeline.render import render_cover, render_pdf


def make_spec(**overrides) -> ProductSpec:
    data = dict(
        title="Sourdough Starter Feeding Log | Bread Baking Tracker | Printable PDF",
        cover_title="Sourdough Starter Log",
        cover_subtitle="Track feedings, rise and flavour",
        niche="baking",
        target_buyer="home sourdough bakers",
        description="A printable log for your starter.\nThis is a digital download; nothing ships.",
        tags=["sourdough log", "Bread Baking Tracker!", "sourdough log", "a" * 30],
        price_usd=4.5,
        accent_color="#8A5A2B",
        pages=[
            Page(heading="Feeding Checklist", intro="Tick each step.", layout="checklist",
                 items=[f"Step {i}" for i in range(12)]),
            Page(heading="Bake Reflections", intro="Write after each bake.", layout="lined",
                 items=["What went well?", "What will you change?"]),
            Page(heading="Feeding Log", intro="One row per feeding.", layout="table",
                 items=["Date", "Flour (g)", "Water (g)", "Rise %", "Notes"]),
        ],
    )
    data.update(overrides)
    return ProductSpec(**data)


def test_cleaned_enforces_marketplace_limits():
    spec = make_spec(title="x" * 200, accent_color="brown", price_usd=0.2).cleaned()
    assert len(spec.title) == 140
    assert spec.tags == ["sourdough log", "bread baking tracker", "a" * 20]
    assert all(len(t) <= 20 for t in spec.tags)
    assert spec.accent_color == "#3B6E8F"
    assert spec.price_usd == 1.0
    assert spec.slug == "sourdough-starter-log"


def test_render_outputs(tmp_path: Path):
    spec = make_spec().cleaned()
    pdf = render_pdf(spec, tmp_path / "p.pdf")
    assert len(PdfReader(pdf).pages) == len(spec.pages) + 1
    from PIL import Image
    cover = render_cover(spec, tmp_path / "c.png")
    assert Image.open(cover).size == (2000, 2000)


def test_ledger_roundtrip(tmp_path: Path):
    path = tmp_path / "ledger.json"
    Ledger(path).add({"slug": "a", "title": "A"})
    assert Ledger(path).titles() == ["A"]


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.headers, self.calls = {}, []

    def post(self, url, json=None, timeout=None):
        q = json["query"]
        self.calls.append((q, json["variables"]))
        if "stagedUploadsCreate" in q:
            return FakeResponse({"data": {"stagedUploadsCreate": {"userErrors": [], "stagedTargets": [
                {"url": "https://upload", "resourceUrl": f"https://res/{len(self.calls)}", "parameters": []}]}}})
        if "fileCreate" in q:
            return FakeResponse({"data": {"fileCreate": {"userErrors": [], "files": [{"id": "gid://File/1"}]}}})
        if "productCreate" in q:
            return FakeResponse({"data": {"productCreate": {"userErrors": [], "product": {
                "id": "gid://Product/9", "handle": "h", "variants": {"nodes": [{"id": "gid://Variant/3"}]}}}}})
        return FakeResponse({"data": {"productVariantsBulkUpdate": {"userErrors": [], "productVariants": []}}})


def test_shopify_publish_flow(tmp_path: Path, monkeypatch):
    spec = make_spec().cleaned()
    pdf, cover = render_pdf(spec, tmp_path / "p.pdf"), render_cover(spec, tmp_path / "c.png")
    monkeypatch.setattr("product_pipeline.publishers.shopify.requests.post",
                        lambda *a, **k: FakeResponse({}, 204))
    session = FakeSession()
    result = ShopifyPublisher(ShopifyConfig("shop", "tok"), session=session).publish(spec, pdf, cover)
    assert result == {"product_id": "gid://Product/9", "handle": "h", "file_id": "gid://File/1"}
    product = next(v for q, v in session.calls if "productCreate" in q)["product"]
    assert product["status"] == "DRAFT"
    assert product["metafields"][0]["value"] == "gid://File/1"
    variants = session.calls[-1][1]["variants"][0]
    assert variants["price"] == "4.50" and variants["inventoryItem"]["requiresShipping"] is False


def test_cli_generate_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "generate_spec", lambda client, niches, titles: make_spec().cleaned())
    monkeypatch.setattr(cli.anthropic, "Anthropic", lambda: None)
    args = ["--count", "2", "--out", str(tmp_path / "out"), "--ledger", str(tmp_path / "l.json")]
    assert cli.main(args) == 0
    slugs = Ledger(tmp_path / "l.json").slugs()
    assert slugs == {"sourdough-starter-log", "sourdough-starter-log-2"}
    assert (tmp_path / "out" / "sourdough-starter-log-2" / "cover.png").exists()


def test_cli_requires_credentials(monkeypatch):
    for var in ("SHOPIFY_STORE", "SHOPIFY_ADMIN_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit):
        cli.main(["--publish", "shopify"])
