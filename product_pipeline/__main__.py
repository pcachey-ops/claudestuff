"""CLI: python -m product_pipeline --count 1 --publish shopify,etsy"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import anthropic

from .generate import generate_spec
from .ledger import Ledger
from .render import render_cover, render_pdf
from .publishers.etsy import EtsyConfig, EtsyPublisher
from .publishers.shopify import ShopifyConfig, ShopifyPublisher

DEFAULT_NICHES = (
    "home organisation, meal planning, personal budgeting, fitness tracking, gardening, "
    "pet care, small business admin, teacher classroom tools, wedding planning, travel planning"
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="product_pipeline", description=__doc__)
    ap.add_argument("--count", type=int, default=1, help="products to make this run")
    ap.add_argument("--publish", default="", help="comma list: shopify,etsy (empty = generate only)")
    ap.add_argument("--activate", action="store_true",
                    help="list as live/active instead of draft (Etsy charges $0.20 per active listing)")
    ap.add_argument("--niches", default=os.getenv("PRODUCT_NICHES", DEFAULT_NICHES))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--ledger", type=Path, default=Path("catalog/ledger.json"))
    args = ap.parse_args(argv)

    targets = {t.strip() for t in args.publish.split(",") if t.strip()}
    publishers = {}
    if "shopify" in targets:
        cfg = ShopifyConfig.from_env()
        if not cfg:
            ap.error("--publish shopify needs SHOPIFY_STORE and SHOPIFY_ADMIN_TOKEN")
        publishers["shopify"] = ShopifyPublisher(cfg)
    if "etsy" in targets:
        cfg = EtsyConfig.from_env()
        if not cfg:
            ap.error("--publish etsy needs ETSY_KEYSTRING, ETSY_SHARED_SECRET, ETSY_REFRESH_TOKEN, "
                     "ETSY_SHOP_ID and ETSY_TAXONOMY_ID")
        publishers["etsy"] = EtsyPublisher(cfg)
    if unknown := targets - {"shopify", "etsy"}:
        ap.error(f"unknown publish target(s): {', '.join(sorted(unknown))}")

    niches = [n.strip() for n in args.niches.split(",") if n.strip()]
    ledger = Ledger(args.ledger)
    client = anthropic.Anthropic()
    failures = 0

    for i in range(args.count):
        spec = generate_spec(client, niches, ledger.titles())
        slug = spec.slug
        n = 2
        while slug in ledger.slugs():
            slug = f"{spec.slug}-{n}"
            n += 1
        folder = args.out / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "spec.json").write_text(spec.model_dump_json(indent=2))
        pdf = render_pdf(spec, folder / f"{slug}.pdf")
        cover = render_cover(spec, folder / "cover.png")
        print(f"[{i + 1}/{args.count}] {spec.title}  (${spec.price_usd:.2f}) -> {folder}")

        entry = {"slug": slug, "title": spec.title, "niche": spec.niche, "price_usd": spec.price_usd}
        for name, pub in publishers.items():
            try:
                entry[name] = pub.publish(spec, pdf, cover, activate=args.activate)
                print(f"    {name}: {entry[name]}")
            except Exception as exc:  # keep going so one marketplace outage doesn't lose the product
                failures += 1
                entry[name] = {"error": str(exc)[:500]}
                print(f"    {name} FAILED: {exc}", file=sys.stderr)
        ledger.add(entry)

    etsy = publishers.get("etsy")
    if etsy and etsy.new_refresh_token and etsy.new_refresh_token != etsy.config.refresh_token:
        print("::notice::Etsy issued a new refresh token; the stored one keeps working until it expires "
              "(90 days). Re-run scripts/etsy_auth.py before then.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
