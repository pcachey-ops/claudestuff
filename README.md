# Digital product pipeline

Twice a week, this repo designs a new printable digital product (planner, tracker,
checklist or worksheet), renders it to a PDF with a 2000×2000 cover image, and lists it on
**Shopify** and **Etsy**. Listings are created as **drafts** by default, so you review each one
before it goes on sale.

```
Claude designs product  →  PDF + cover image  →  Shopify draft  +  Etsy draft  →  catalog/ledger.json
```

`catalog/ledger.json` records every product so new ones never repeat old ones, and the files
are kept in `output/<slug>/`.

## What it costs

| Item | Cost |
|---|---|
| Claude API, one product per call | roughly $0.10–0.40 |
| Etsy listing fee | $0.20, charged only when a listing goes active (drafts are free) |
| Etsy transaction + payment fees | about 6.5% + 3% + $0.25 per sale |
| GitHub Actions | free on public repos; private repos use your free minutes |

At $4–8 a product, one sale per listing covers its costs. Realistic expectations: most listings
sell little or nothing, and a few do most of the selling. Over months the catalog grows, and
the products that sell show you which niches to narrow `PRODUCT_NICHES` towards.

## Setup

### 1. Run locally first (no marketplaces)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m product_pipeline --count 1          # writes output/<slug>/ and catalog/ledger.json
```

Open the PDF and `cover.png` and check the quality before connecting a store.

### 2. Shopify

1. Shopify admin → **Settings → Apps and sales channels → Develop apps → Create an app**.
2. Admin API scopes: `write_products`, `write_files`.
3. Install the app and copy the Admin API access token (`shpat_...`).
4. Install Shopify's free **Digital Downloads** app. The pipeline uploads the PDF to
   **Content → Files** and links it from the product's `custom.download_file` metafield, but
   Shopify only emails a download to buyers once the file is attached in Digital Downloads.
   Attaching it is your review step: when you approve a draft, attach the file and set the
   product to Active.

### 3. Etsy

1. Create an app at <https://www.etsy.com/developers/your-apps>, with
   `http://localhost:3003/callback` as a callback URL. Copy the keystring and shared secret.
2. Run the one-time auth helper, which prints your refresh token and shop id:
   ```bash
   ETSY_KEYSTRING=... ETSY_SHARED_SECRET=... python scripts/etsy_auth.py
   ```
3. Choose a taxonomy (category) id for your listings, for example the id for
   *Paper & Party Supplies → Paper → Calendars & Planners*. Etsy's `getSellerTaxonomyNodes`
   endpoint lists them all.
4. **The refresh token expires after 90 days.** Re-run the helper and update the secret before then.

Etsy listings get a short note saying the design was made with AI-assisted tools, as Etsy's
creativity standards require.

### 4. Automate it with GitHub Actions

Under **Settings → Secrets and variables → Actions**:

| Secrets | Variables |
|---|---|
| `ANTHROPIC_API_KEY` | `PUBLISH_TARGETS`, e.g. `shopify,etsy` (blank = generate only) |
| `SHOPIFY_STORE`, `SHOPIFY_ADMIN_TOKEN` | `PRODUCTS_PER_RUN` (default `2`) |
| `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET` | `ETSY_TAXONOMY_ID` |
| `ETSY_REFRESH_TOKEN`, `ETSY_SHOP_ID` | `PRODUCT_NICHES`, a comma-separated list |

The workflow `.github/workflows/make-products.yml` runs on Mondays and Thursdays. You can also
run it from the **Actions** tab. Each run commits the new products to the repo.

## CLI

```
python -m product_pipeline [--count N] [--publish shopify,etsy] [--activate]
                           [--niches "a, b, c"] [--out output] [--ledger catalog/ledger.json]
```

`--activate` lists products as live immediately and skips your review. Only use it once you
trust the output, because Etsy charges the listing fee on activation.

## Layout

```
product_pipeline/
  generate.py          Claude designs the product (structured output → ProductSpec)
  models.py            ProductSpec / Page, plus enforcement of marketplace limits
  render.py            PDF (reportlab) and cover image (Pillow)
  publishers/shopify.py  Admin GraphQL: staged uploads, productCreate, pricing
  publishers/etsy.py     Open API v3: draft listing, image, digital file
  ledger.py            append-only catalog
scripts/etsy_auth.py   one-time Etsy OAuth helper
tests/                 offline tests (no API calls)
```
