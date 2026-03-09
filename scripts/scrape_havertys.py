"""
Haverty's furniture catalog scraper.
Fetches products from the Havertys Magento GraphQL API across 4 categories
(Sofas & Sleepers, Sectionals, Recliners, Chairs), deduplicates by SKU,
classifies types, extracts collections, and outputs a unified catalog JSON.

Requires: curl_cffi (pip install curl_cffi)
  - Havertys uses TLS fingerprinting that blocks standard HTTP clients.
  - curl_cffi impersonates Chrome's TLS fingerprint to bypass this.

Usage:
    python scrape_havertys.py
"""

import json
import os
import random
import re
import sys
import time

from curl_cffi import requests as curl_requests

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app')
OUTPUT_FILE = os.path.join(BACKEND_DIR, 'havertys_catalog.json')

GRAPHQL_ENDPOINT = 'https://www.havertys.com/api/cors-graphql'

HEADERS = {
    'Content-Type': 'application/json',
    'Store': 'default',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.havertys.com',
    'Referer': 'https://www.havertys.com/',
}

# Categories to scrape
CATEGORIES = [
    {'name': 'Sofas & Sleepers', 'url_path': 'living-room/sofas-sleepers'},
    {'name': 'Sectionals',       'url_path': 'living-room/sectionals'},
    {'name': 'Recliners',        'url_path': 'living-room/recliners'},
    {'name': 'Chairs',           'url_path': 'living-room/chairs'},
]

PAGE_SIZE = 20

# Type classification — order matters (most specific first)
TYPE_KEYWORDS = [
    ('sleeper sectional', 'Sectional'),
    ('reclining sectional', 'Sectional'),
    ('power sectional', 'Sectional'),
    ('sectional', 'Sectional'),
    ('sleeper sofa', 'Sleeper'),
    ('queen sleeper', 'Sleeper'),
    ('twin sleeper', 'Sleeper'),
    ('full sleeper', 'Sleeper'),
    ('king sleeper', 'Sleeper'),
    ('sleeper', 'Sleeper'),
    ('power reclining sofa', 'Recliner'),
    ('power reclining loveseat', 'Recliner'),
    ('reclining sofa', 'Recliner'),
    ('reclining loveseat', 'Recliner'),
    ('power recliner', 'Recliner'),
    ('rocker recliner', 'Recliner'),
    ('wall recliner', 'Recliner'),
    ('recliner', 'Recliner'),
    ('swivel chair', 'Chair'),
    ('accent chair', 'Chair'),
    ('club chair', 'Chair'),
    ('arm chair', 'Chair'),
    ('pushback chair', 'Chair'),
    ('push back chair', 'Chair'),
    ('chair and a half', 'Chair'),
    ('chair', 'Chair'),
    ('loveseat', 'Loveseat'),
    ('love seat', 'Loveseat'),
    ('ottoman', 'Ottoman'),
    ('sofa', 'Sofa'),
    ('couch', 'Sofa'),
]

# Exclusion keywords — skip non-seating items
EXCLUDE_KEYWORDS = [
    'table', 'desk', 'bookcase', 'shelf', 'rug', 'lamp', 'pillow',
    'throw', 'mirror', 'nightstand', 'dresser', 'bed', 'headboard',
    'bench', 'console', 'credenza', 'buffet', 'hutch', 'entertainment',
    'tv stand', 'end table', 'coffee table', 'side table', 'accent table',
]

# Words to strip when extracting collection name
COLLECTION_STRIP_WORDS = {
    'sofa', 'sectional', 'chair', 'swivel', 'accent', 'arm', 'armchair',
    'chaise', 'ottoman', 'loveseat', 'settee', 'couch', 'recliner',
    'reclining', 'sleeper', 'power', 'rocker', 'wall', 'pushback',
    'push', 'back', 'queen', 'twin', 'full', 'king',
    'with', 'piece', 'and', 'the', 'in', 'w', 'w/', 'a', 'half',
    'pc', 'plus', 'standard', 'oversized', 'small', 'large', 'xl',
    'right', 'left', 'facing', 'raf', 'laf',
    'living', 'room', 'set', 'collection',
}


# ─── GraphQL Helpers ──────────────────────────────────────────────────────────

def gql_request(query: str, retries: int = 3) -> dict:
    """Execute a GraphQL query with retries using curl_cffi (bypasses TLS fingerprinting)."""
    for attempt in range(retries):
        try:
            resp = curl_requests.post(
                GRAPHQL_ENDPOINT,
                json={'query': query},
                headers=HEADERS,
                impersonate='chrome',
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if 'errors' in data:
                print(f"  GraphQL errors: {data['errors']}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            return data.get('data', {})
        except Exception as e:
            print(f"  Request error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)
            else:
                print(f"  FAILED after {retries} attempts, returning empty")
                return {}
    return {}


def get_category_uid(url_path: str) -> tuple:
    """Get category UID and product count for a given url_path."""
    query = f'''{{
        categoryList(filters: {{ url_path: {{ eq: "{url_path}" }} }}) {{
            uid
            name
            product_count
        }}
    }}'''
    data = gql_request(query)
    cats = data.get('categoryList', [])
    if not cats:
        return None, 0
    cat = cats[0]
    return cat.get('uid'), cat.get('product_count', 0)


def fetch_products_page(category_uid: str, page: int) -> dict:
    """Fetch a single page of products for a category."""
    query = f'''{{
        products(
            filter: {{ category_uid: {{ eq: "{category_uid}" }} }}
            pageSize: {PAGE_SIZE}
            currentPage: {page}
        ) {{
            total_count
            items {{
                name
                sku
                url_key
                categories {{
                    name
                    url_path
                }}
                price_range {{
                    minimum_price {{
                        regular_price {{ value }}
                        final_price {{ value }}
                        discount {{ amount_off percent_off }}
                    }}
                }}
                image {{ url label }}
                small_image {{ url label }}
            }}
            page_info {{
                current_page
                page_size
                total_pages
            }}
        }}
    }}'''
    return gql_request(query)


# ─── Classification Helpers ───────────────────────────────────────────────────

def classify_type(name: str, category_url_path: str):
    """Classify product type from name and category."""
    name_lower = name.lower()

    # Check exclusions first
    for kw in EXCLUDE_KEYWORDS:
        if kw in name_lower:
            return None

    # Try name-based classification first (most specific)
    for keyword, ftype in TYPE_KEYWORDS:
        if keyword in name_lower:
            return ftype

    # Fall back to category-based classification
    cat_lower = category_url_path.lower()
    if 'sectional' in cat_lower:
        return 'Sectional'
    if 'sofa' in cat_lower or 'sleeper' in cat_lower:
        return 'Sofa'
    if 'recliner' in cat_lower:
        return 'Recliner'
    if 'chair' in cat_lower:
        return 'Chair'

    return 'Sofa'  # Default for living room items


def extract_collection(name: str) -> str:
    """Extract collection name from product name by stripping type keywords."""
    # Remove parenthetical info like (Power Reclining)
    cleaned = re.sub(r'\([^)]*\)', '', name).strip()
    # Remove trailing numbers (e.g., piece counts)
    cleaned = re.sub(r'\b\d+[-\s]*(pc|piece|sect)?\b', '', cleaned, flags=re.IGNORECASE).strip()

    words = cleaned.split()
    collection_words = []
    for w in words:
        if w.lower().rstrip('s').rstrip(',') in COLLECTION_STRIP_WORDS:
            break
        collection_words.append(w)

    collection = ' '.join(collection_words).strip(' -,')

    # If we got nothing or just 1 char, use first 2 words of original name
    if len(collection) < 2:
        parts = name.split()
        collection = ' '.join(parts[:2]) if len(parts) >= 2 else name

    return collection


# ─── Image Validation ─────────────────────────────────────────────────────────

def validate_images(items: list, sample_size: int = 20) -> tuple:
    """Validate a sample of image URLs using curl_cffi. Returns (valid, total_sampled)."""
    if not items:
        return 0, 0

    sample = random.sample(items, min(sample_size, len(items)))
    valid = 0
    for item in sample:
        url = item.get('image_url', '')
        if not url:
            continue
        try:
            resp = curl_requests.head(url, impersonate='chrome', timeout=10)
            content_type = resp.headers.get('content-type', '')
            if resp.status_code == 200 and 'image' in content_type:
                valid += 1
            elif resp.status_code in (403, 405):
                # Some CDNs block HEAD, try GET with range header
                resp2 = curl_requests.get(
                    url, impersonate='chrome', timeout=10,
                    headers={'Range': 'bytes=0-1023'}
                )
                ct2 = resp2.headers.get('content-type', '')
                if resp2.status_code in (200, 206) and 'image' in ct2:
                    valid += 1
                else:
                    print(f"  INVALID (GET {resp2.status_code}): {url[:100]}")
            else:
                print(f"  INVALID ({resp.status_code}, {content_type}): {url[:100]}")
        except Exception as e:
            print(f"  ERROR checking {url[:80]}: {e}")

    return valid, len(sample)


# ─── Main Scraper ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Haverty's Furniture Catalog Scraper")
    print("  Using curl_cffi for TLS fingerprint bypass")
    print("=" * 70)
    print()

    all_products = {}  # SKU -> product dict (for dedup)

    # ── Step 1 & 2: Fetch each category ──
    for cat_info in CATEGORIES:
        cat_name = cat_info['name']
        url_path = cat_info['url_path']

        print(f"[{cat_name}] Looking up category UID for '{url_path}'...")
        uid, product_count = get_category_uid(url_path)

        if not uid:
            print(f"  ERROR: Could not find category UID for '{url_path}'. Skipping.")
            print()
            continue

        print(f"  Found UID={uid}, product_count={product_count}")

        # Paginate through all products
        page = 1
        total_pages = 1
        cat_items = 0

        while page <= total_pages:
            print(f"  Fetching page {page}/{total_pages}...")
            data = fetch_products_page(uid, page)

            products_data = data.get('products', {})
            items = products_data.get('items', [])
            page_info = products_data.get('page_info', {})
            total_pages = page_info.get('total_pages', 1)
            total_count = products_data.get('total_count', 0)

            if page == 1:
                print(f"  Total products: {total_count}, pages: {total_pages}")

            for item in items:
                sku = item.get('sku', '').strip()
                name = item.get('name', '').strip()
                url_key = item.get('url_key', '')

                if not sku or not name:
                    continue

                # Skip duplicates (keep first occurrence)
                if sku in all_products:
                    continue

                # Classify type
                ftype = classify_type(name, url_path)
                if ftype is None:
                    continue  # Excluded item

                # Extract pricing
                price_range = item.get('price_range', {})
                min_price = price_range.get('minimum_price', {})
                regular = min_price.get('regular_price', {}).get('value', 0)
                final = min_price.get('final_price', {}).get('value', 0)
                discount = min_price.get('discount', {})
                amount_off = discount.get('amount_off', 0) or 0

                on_sale = amount_off > 0 and regular > final

                # Image URL — prefer main image, fall back to small_image
                image_data = item.get('image') or item.get('small_image') or {}
                image_url = image_data.get('url', '')

                # Build product URL
                product_url = f"https://www.havertys.com/products/product-page/{url_key}" if url_key else ''

                # Extract collection
                collection = extract_collection(name)

                product = {
                    'name': name,
                    'sku': sku,
                    'price': round(final or regular, 2),
                    'compare_at_price': round(regular, 2) if on_sale else round(final or regular, 2),
                    'on_sale': on_sale,
                    'collection': collection,
                    'color': 'Varies',
                    'url': product_url,
                    'image_url': image_url,
                    'category': 'Living',
                    'type': ftype,
                    'brand': 'Havertys',
                    'material': 'Fabric',
                }
                all_products[sku] = product
                cat_items += 1

            page += 1
            # Polite delay between pages
            time.sleep(0.5)

        print(f"  -> {cat_items} new items from {cat_name}")
        print()

    # ── Step 3: Deduplicate (already done via SKU dict) ──
    catalog = list(all_products.values())
    print(f"Total unique products after dedup: {len(catalog)}")

    # ── Sort by type, then name ──
    type_order = ['Sectional', 'Sofa', 'Sleeper', 'Loveseat', 'Recliner', 'Chair', 'Ottoman']
    catalog.sort(key=lambda p: (
        type_order.index(p['type']) if p['type'] in type_order else 99,
        p['name']
    ))

    # ── Step 5: Validate image URLs ──
    print()
    print("Validating image URLs (sample of 20)...")
    valid, sampled = validate_images(catalog, sample_size=20)
    print(f"  Image validation: {valid}/{sampled} valid ({100*valid//max(sampled,1)}%)")

    # ── Write output ──
    print()
    print(f"Writing {len(catalog)} products to {OUTPUT_FILE}")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total products: {len(catalog)}")
    print()

    # By type
    type_counts = {}
    for p in catalog:
        t = p['type']
        type_counts[t] = type_counts.get(t, 0) + 1
    print("  By type:")
    for t in type_order:
        if t in type_counts:
            print(f"    {t:15s} {type_counts[t]:4d}")
    print()

    # By sale status
    on_sale_count = sum(1 for p in catalog if p['on_sale'])
    print(f"  On sale: {on_sale_count}")
    print(f"  Regular price: {len(catalog) - on_sale_count}")

    # Price range
    if catalog:
        prices = [p['price'] for p in catalog if p['price'] > 0]
        if prices:
            print(f"  Price range: ${min(prices):,.2f} - ${max(prices):,.2f}")

    # Collections
    collections = set(p['collection'] for p in catalog)
    print(f"  Unique collections: {len(collections)}")

    # Image stats
    with_images = sum(1 for p in catalog if p['image_url'])
    print(f"  Products with images: {with_images}/{len(catalog)}")

    print()
    print(f"Output saved to: {OUTPUT_FILE}")
    print("Done!")


if __name__ == '__main__':
    main()
