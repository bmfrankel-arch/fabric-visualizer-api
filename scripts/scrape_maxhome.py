"""
Max Home furniture catalog scraper.
Fetches products from Bush Home Shopify store (consumer retailer for Max Home),
splits variants into individual entries, and outputs a catalog JSON.

Usage:
    python scrape_maxhome.py
"""

import json
import os
import re
import sys

import httpx

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app')
OUTPUT_FILE = os.path.join(BACKEND_DIR, 'maxhome_catalog.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/html,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

API_URL = 'https://www.bushhome.com/collections/max-home-furniture-collection/products.json?limit=250'

# Type classification by keyword priority
TYPE_KEYWORDS = [
    ('accent chair', 'Chair'),
    ('chair', 'Chair'),
    ('loveseat', 'Loveseat'),
    ('love seat', 'Loveseat'),
    ('ottoman', 'Ottoman'),
    ('storage ottoman', 'Ottoman'),
    ('sofa', 'Sofa'),
    ('couch', 'Sofa'),
]

# Variant-to-color/material mapping
# Shopify variant titles may be "Buffed Camel Leather" or "Iron Gray Chenille Fabric"
VARIANT_INFO = {
    'buffed camel leather': {
        'color': 'Buffed Camel',
        'material': 'Leather',
        'color_suffix': 'Buffed Camel Leather',
    },
    'iron gray chenille fabric': {
        'color': 'Iron Gray',
        'material': 'Fabric',
        'color_suffix': 'Iron Gray Chenille',
    },
    'iron gray chenille': {
        'color': 'Iron Gray',
        'material': 'Fabric',
        'color_suffix': 'Iron Gray Chenille',
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def classify_type(title: str) -> str:
    """Determine furniture type from product title."""
    lower = title.lower()
    for keyword, ftype in TYPE_KEYWORDS:
        if keyword in lower:
            return ftype
    return 'Sofa'  # default


def is_bundle_product(title: str, handle: str) -> bool:
    """Return True if the product is a bundle/set (should be excluded).

    Individual pieces have handles like:
      - 77w-sofa-mxj177xx
      - 54w-loveseat-mxj154xx
      - 32w-accent-chair-mxk132xx
      - ottoman-w-storage-and-tray-mxo130xx

    Bundles have handles like:
      - 54w-loveseat-w-ottoman-max004xx
      - 77w-sofa-54w-loveseat-and-ottoman-max005xx
      - 77w-sofa-32w-accent-chair-and-ottoman-max006xx
      - 77w-sofa-54w-loveseat-32w-accent-chair-and-ottoman-max007xx
      - 32w-accent-chair-w-ottoman-max002xx
      - 77w-sofa-w-ottoman-max003xx

    Strategy: bundles mention multiple furniture types, or contain commas
    separating items, or use "and" to join distinct products.
    """
    lower = title.lower()

    # Explicit "Set" or "+" in name
    if ' set' in lower or lower.endswith(' set'):
        return True
    if '+' in title:
        return True

    # Piece count like "3-Piece"
    if re.search(r'\d+[-\s]?piece', lower):
        return True

    # Commas in title almost always mean bundled items
    # e.g. "77W Sofa, 54W Loveseat, and Storage Ottoman"
    if ',' in title:
        return True

    # Title mentions multiple distinct furniture types joined by "and"
    # But we need to exclude "Ottoman with Tray" (single product with "with")
    # and "Accent Chair" (single product). The pattern is: multiple furniture
    # nouns separated by "and".
    furniture_nouns = ['sofa', 'loveseat', 'love seat', 'chair', 'ottoman']
    found_types = []
    for noun in furniture_nouns:
        if noun in lower:
            found_types.append(noun)
    # If title contains 2+ distinct furniture types, it's a bundle
    if len(found_types) >= 2:
        return True

    return False


def image_area(img: dict) -> int:
    """Calculate image area from width/height for sorting."""
    w = img.get('width', 0) or 0
    h = img.get('height', 0) or 0
    return w * h


def best_image_url(images: list[dict]) -> str:
    """Pick the largest image URL from a Shopify images list."""
    if not images:
        return ''
    best = max(images, key=image_area)
    return best.get('src', '')


def variant_color_key(variant_title: str) -> str:
    """Normalize variant title to a key for looking up color/material info."""
    return variant_title.strip().lower()


def build_display_name(base_title: str, variant_title: str, ftype: str) -> str:
    """Build a clean display name like 'Max 77W Sofa - Iron Gray Chenille'."""
    # The base title already has the furniture type; append the variant
    return f"{base_title.strip()} - {variant_title.strip()}"


def validate_image_url(client: httpx.Client, url: str) -> bool:
    """Validate that an image URL is reachable."""
    if not url:
        return False
    try:
        resp = client.head(url, follow_redirects=True, timeout=10)
        if resp.status_code == 200:
            ct = resp.headers.get('content-type', '')
            return ct.startswith('image/')
        # Some CDNs block HEAD; fall back to GET with range
        resp = client.get(url, follow_redirects=True, timeout=10,
                          headers={'Range': 'bytes=0-1023'})
        return resp.status_code in (200, 206)
    except (httpx.HTTPError, httpx.TimeoutException):
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Max Home Catalog Scraper (via Bush Home Shopify)")
    print("=" * 60)

    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30)

    try:
        # Step 1: Fetch products from Shopify API
        print(f"\nFetching from: {API_URL}")
        resp = client.get(API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_products = data.get('products', [])
        print(f"  Raw products from API: {len(raw_products)}")

        # Step 2: Filter and process
        items = []
        skipped_bundles = []
        skipped_no_variants = 0
        skipped_no_image = 0

        for prod in raw_products:
            title = prod.get('title', '').strip()
            handle = prod.get('handle', '')
            variants = prod.get('variants', [])
            images = prod.get('images', [])

            # Skip bundles/sets
            if is_bundle_product(title, handle):
                skipped_bundles.append(title)
                continue

            # Must have images
            if not images:
                skipped_no_image += 1
                print(f"  SKIP (no image): {title}")
                continue

            # Must have variants
            if not variants:
                skipped_no_variants += 1
                print(f"  SKIP (no variants): {title}")
                continue

            # Classify type from base title
            ftype = classify_type(title)
            product_url = f"https://www.bushhome.com/products/{handle}"

            # Best image for this product
            img_url = best_image_url(images)

            # Create one entry per variant
            for variant in variants:
                variant_title = variant.get('title', '').strip()
                variant_key = variant_color_key(variant_title)
                sku = variant.get('sku', '') or handle

                # Parse price
                try:
                    price = float(variant.get('price', '0'))
                except (ValueError, TypeError):
                    price = 0.0

                try:
                    compare_at = float(variant.get('compare_at_price', '0') or '0')
                except (ValueError, TypeError):
                    compare_at = 0.0

                on_sale = compare_at > 0 and price < compare_at

                # Look up color/material from variant info mapping
                info = VARIANT_INFO.get(variant_key, {})
                color = info.get('color', variant_title)
                material = info.get('material', 'Fabric')
                color_suffix = info.get('color_suffix', variant_title)

                # Check if variant has its own featured image
                variant_image_id = variant.get('featured_image', {})
                if isinstance(variant_image_id, dict) and variant_image_id.get('src'):
                    var_img_url = variant_image_id['src']
                else:
                    var_img_url = img_url

                display_name = build_display_name(title, color_suffix, ftype)

                item = {
                    'name': display_name,
                    'sku': sku,
                    'price': price,
                    'compare_at_price': compare_at if compare_at > 0 else price,
                    'on_sale': on_sale,
                    'collection': 'Max Collection',
                    'color': color,
                    'url': product_url,
                    'image_url': var_img_url,
                    'category': 'Living',
                    'type': ftype,
                    'brand': 'Max Home',
                    'material': material,
                }
                items.append(item)

        print(f"\n  Kept individual products: {len(items)} (from variants)")
        if skipped_bundles:
            print(f"  Skipped bundles/sets ({len(skipped_bundles)}):")
            for b in skipped_bundles:
                print(f"    - {b}")
        if skipped_no_image:
            print(f"  Skipped (no image): {skipped_no_image}")
        if skipped_no_variants:
            print(f"  Skipped (no variants): {skipped_no_variants}")

        # Step 3: Validate image URLs
        print(f"\n=== Validating {len(items)} image URLs ===")
        valid_items = []
        invalid_count = 0

        for i, item in enumerate(items):
            if validate_image_url(client, item['image_url']):
                valid_items.append(item)
            else:
                print(f"  INVALID IMAGE: {item['name']} -> {item['image_url'][:80]}...")
                invalid_count += 1

        print(f"  Valid: {len(valid_items)}, Invalid: {invalid_count}")

        # Step 4: Sort by type then name
        type_order = {
            'Sofa': 0, 'Loveseat': 1, 'Chair': 2, 'Ottoman': 3,
        }
        valid_items.sort(key=lambda p: (type_order.get(p['type'], 99), p['name']))

        # Step 5: Save
        output_path = os.path.abspath(OUTPUT_FILE)

        existing_count = 0
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                existing_count = len(existing)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(valid_items, f, indent=2, ensure_ascii=False)

        # Step 6: Summary
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Source: Bush Home Shopify (Max Home collection)")
        print(f"  Raw products from API: {len(raw_products)}")
        print(f"  Bundles/sets excluded: {len(skipped_bundles)}")
        print(f"  Variant entries created: {len(items)}")
        print(f"  After image validation: {len(valid_items)}")
        if existing_count:
            print(f"  Previous catalog: {existing_count} items")
        print(f"  Final catalog: {len(valid_items)} items")
        print(f"  Saved to: {output_path}")

        # Type breakdown
        print(f"\n  Type breakdown:")
        type_counts: dict[str, int] = {}
        for p in valid_items:
            t = p['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        for t in sorted(type_counts, key=lambda x: type_order.get(x, 99)):
            print(f"    {t}: {type_counts[t]}")

        # List all items
        print(f"\n  All items:")
        for p in valid_items:
            sale_tag = " (SALE)" if p['on_sale'] else ""
            print(f"    [{p['type']}] {p['name']} — ${p['price']:.2f} — {p['material']}{sale_tag}")

    finally:
        client.close()


if __name__ == '__main__':
    main()
