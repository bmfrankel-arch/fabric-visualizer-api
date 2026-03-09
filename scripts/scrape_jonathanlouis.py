"""
Jonathan Louis furniture catalog scraper.
Fetches products from 3 Shopify stores (Seldens, Schneiderman's, City Home PDX),
deduplicates across stores, and outputs a unified catalog JSON.

Usage:
    python scrape_jonathanlouis.py
"""

import json
import os
import re
import sys
import time
from difflib import SequenceMatcher

import httpx

# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app')
OUTPUT_FILE = os.path.join(BACKEND_DIR, 'jonathanlouis_catalog.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/html,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Shopify stores with Jonathan Louis collections
STORES = [
    {
        'name': 'Seldens',
        'domain': 'seldens.com',
        'url': 'https://seldens.com/collections/jonathan-louis/products.json?limit=250',
        'vendor_filter': 'Jonathan Louis',  # vendor field = "Jonathan Louis"
    },
    {
        'name': "Schneiderman's",
        'domain': 'schneidermans.com',
        'url': 'https://schneidermans.com/collections/jonathan-louis/products.json?limit=250',
        'vendor_filter': None,  # vendor = "Schneiderman's Furniture", so skip vendor check
    },
    {
        'name': 'City Home PDX',
        'domain': 'cityhomepdx.com',
        'url': 'https://cityhomepdx.com/collections/jonathan-louis-furniture-portland-oregon/products.json?limit=250',
        'vendor_filter': 'Jonathan Louis',
    },
]

# Furniture types we want, ordered from most specific to least
TYPE_KEYWORDS = [
    ('swivel chair', 'Swivel Chair'),
    ('swivel', 'Swivel Chair'),
    ('accent chair', 'Chair'),
    ('arm chair', 'Chair'),
    ('armchair', 'Chair'),
    ('lounge chair', 'Chair'),
    ('club chair', 'Chair'),
    ('chair', 'Chair'),
    ('settee', 'Loveseat'),
    ('loveseat', 'Loveseat'),
    ('love seat', 'Loveseat'),
    ('sectional', 'Sectional'),
    ('chaise', 'Chaise'),
    ('ottoman', 'Ottoman'),
    ('sofa', 'Sofa'),
    ('couch', 'Sofa'),
]

# Words to strip when extracting collection name
TYPE_WORDS = {
    'sofa', 'sectional', 'chair', 'swivel', 'accent', 'arm', 'armchair',
    'chaise', 'ottoman', 'loveseat', 'settee', 'couch', 'estate',
    'reversible', 'with', 'piece', 'and', 'the', 'in', 'w', 'w/',
    'pc', 'plus', 'standard', 'oversized',
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def classify_type(title: str, product_type: str = '') -> str:
    """Determine furniture type from title and product_type field."""
    combined = f"{title} {product_type}".lower()
    for keyword, ftype in TYPE_KEYWORDS:
        if keyword in combined:
            return ftype
    return 'Sofa'  # default


def extract_collection(title: str) -> str:
    """Extract collection name from product title.

    e.g. "Callum Sectional" -> "Callum"
         "Dawn 3-Piece Sectional" -> "Dawn"
         "Janet Sectional with Reversible Chaise" -> "Janet"
         "Anderson Estate Sofa" -> "Anderson"
    """
    # Remove piece counts like "3-Piece", "2 Piece"
    cleaned = re.sub(r'\d+[-\s]?piece', '', title, flags=re.IGNORECASE)
    # Remove parenthetical notes
    cleaned = re.sub(r'\(.*?\)', '', cleaned)
    # Split into words
    words = cleaned.strip().split()

    # Take words from the start until we hit a type keyword
    collection_words = []
    for w in words:
        if w.lower().rstrip('s') in TYPE_WORDS or w.lower() in TYPE_WORDS:
            break
        collection_words.append(w)

    return ' '.join(collection_words).strip() if collection_words else words[0] if words else ''


def extract_configuration(title: str, ftype: str) -> str:
    """Determine configuration from title."""
    lower = title.lower()
    if 'reversible chaise' in lower:
        return 'Reversible Chaise'
    # Check for piece count
    piece_match = re.search(r'(\d+)[-\s]?piece', lower)
    if piece_match:
        return f"{piece_match.group(1)}-Piece"
    if ftype == 'Swivel Chair':
        return 'Swivel'
    if ftype == 'Sectional':
        return 'Multi-Piece'
    return 'Stationary'


def extract_pieces(title: str) -> int:
    """Extract number of pieces from title."""
    match = re.search(r'(\d+)[-\s]?piece', title, re.IGNORECASE)
    return int(match.group(1)) if match else 1


def extract_color(title: str, tags: list[str]) -> str:
    """Try to extract color from tags or title."""
    # Common color words
    colors = [
        'pebble', 'stone', 'oatmeal', 'mist', 'snow', 'graphite', 'olive',
        'moss', 'linen', 'almond', 'ginger', 'vintage', 'pearl', 'sand',
        'naval', 'prairie', 'mineral', 'amaretto', 'sage', 'cream', 'ivory',
        'charcoal', 'gray', 'grey', 'white', 'black', 'blue', 'green',
        'brown', 'tan', 'beige', 'natural', 'wheat', 'denim', 'indigo',
        'teal', 'rust', 'clay', 'taupe', 'smoke', 'fog', 'cloud',
    ]

    # Check tags for color mentions
    for tag in tags:
        tag_lower = tag.lower()
        for color in colors:
            if color in tag_lower:
                return color.capitalize()

    return 'Varies'


def normalize_for_dedup(title: str, ftype: str) -> str:
    """Normalize a product title for deduplication comparison.

    Keeps the classified type appended so that different product types
    from the same collection (e.g. "Lincoln Sofa" vs "Lincoln Chair")
    are NOT merged.
    """
    lower = title.lower().strip()
    # Remove piece counts
    lower = re.sub(r'\d+[-\s]?piece', '', lower)
    # Remove parenthetical notes
    lower = re.sub(r'\(.*?\)', '', lower)
    # Remove common filler/qualifier words but keep collection + type identity
    words = lower.split()
    filtered = [w for w in words if w.rstrip('s') not in TYPE_WORDS and w not in TYPE_WORDS]
    collection_part = ' '.join(filtered).strip()
    # Append the classified type so different product categories stay separate
    return f"{collection_part}|{ftype.lower()}"


def image_size(img: dict) -> int:
    """Calculate image area from width/height. Used for preferring larger images."""
    w = img.get('width', 0) or 0
    h = img.get('height', 0) or 0
    return w * h


def validate_image_url(client: httpx.Client, url: str) -> bool:
    """Validate that an image URL returns a successful response."""
    if not url:
        return False
    try:
        resp = client.head(url, follow_redirects=True, timeout=10)
        return resp.status_code == 200
    except (httpx.HTTPError, httpx.TimeoutException):
        return False


def similar(a: str, b: str) -> float:
    """Return similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


# ─── Shopify API Fetcher ─────────────────────────────────────────────────────

def fetch_store_products(client: httpx.Client, store: dict) -> list[dict]:
    """Fetch and parse products from a single Shopify store."""
    store_name = store['name']
    domain = store['domain']
    url = store['url']
    vendor_filter = store['vendor_filter']

    print(f"\n--- Fetching from {store_name} ({domain}) ---")

    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f"  ERROR fetching {store_name}: {e}")
        return []

    data = resp.json()
    raw_products = data.get('products', [])
    print(f"  Raw products from API: {len(raw_products)}")

    # Handle pagination if store has more than 250 products
    page = 2
    while len(raw_products) % 250 == 0 and len(raw_products) > 0:
        next_url = f"{url}&page={page}"
        try:
            resp = client.get(next_url, timeout=30)
            resp.raise_for_status()
            next_products = resp.json().get('products', [])
            if not next_products:
                break
            raw_products.extend(next_products)
            page += 1
        except (httpx.HTTPError, httpx.TimeoutException):
            break

    # Words that indicate non-furniture items we don't want
    EXCLUDE_WORDS = {'bed', 'headboard', 'nightstand', 'dresser', 'mirror', 'bench',
                     'table', 'desk', 'bookcase', 'shelf', 'rug', 'lamp', 'pillow'}

    items = []
    skipped_vendor = 0
    skipped_no_image = 0
    skipped_no_price = 0
    skipped_excluded = 0

    for prod in raw_products:
        title = prod.get('title', '').strip()
        handle = prod.get('handle', '')
        vendor = prod.get('vendor', '')
        product_type = prod.get('product_type', '')
        tags = prod.get('tags', [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]

        # Filter to Jonathan Louis products
        # For Schneiderman's, vendor is store name, so we skip vendor check
        # since the collection URL already filters to JL
        if vendor_filter and vendor_filter.lower() not in vendor.lower():
            # Also check tags for "Jonathan Louis"
            tag_str = ' '.join(tags).lower()
            if 'jonathan louis' not in tag_str and 'jonathan louis' not in title.lower():
                skipped_vendor += 1
                continue

        # Exclude non-seating items (beds, tables, etc.)
        title_lower = title.lower()
        if any(word in title_lower.split() for word in EXCLUDE_WORDS):
            skipped_excluded += 1
            continue

        # Get first variant for pricing
        variants = prod.get('variants', [])
        if not variants:
            skipped_no_price += 1
            continue

        variant = variants[0]
        try:
            price = float(variant.get('price', '0'))
        except (ValueError, TypeError):
            price = 0.0

        try:
            compare_at = float(variant.get('compare_at_price', '0') or '0')
        except (ValueError, TypeError):
            compare_at = 0.0

        # Get the best (largest) image
        images = prod.get('images', [])
        if not images:
            skipped_no_image += 1
            continue

        # Sort images by size (area), prefer largest
        best_image = max(images, key=image_size)
        image_url = best_image.get('src', '')
        img_w = best_image.get('width', 0) or 0
        img_h = best_image.get('height', 0) or 0

        if not image_url:
            skipped_no_image += 1
            continue

        # Classify type
        ftype = classify_type(title, product_type)
        collection = extract_collection(title)
        configuration = extract_configuration(title, ftype)
        pieces = extract_pieces(title)
        color = extract_color(title, tags)

        # Build product URL
        product_url = f"https://{domain}/products/{handle}"

        # On sale if compare_at > price and compare_at is set
        on_sale = compare_at > 0 and price < compare_at

        item = {
            'name': title,
            'sku': handle,
            'price': price,
            'compare_at_price': compare_at if compare_at > 0 else price,
            'on_sale': on_sale,
            'collection': collection,
            'color': color,
            'url': product_url,
            'image_url': image_url,
            'category': 'Living',
            'type': ftype,
            'brand': 'Jonathan Louis',
            'material': 'Fabric',
            'configuration': configuration,
            'pieces': pieces,
            # Internal metadata for dedup (not saved to final JSON)
            '_store': store_name,
            '_image_area': img_w * img_h,
            '_image_width': img_w,
            '_image_height': img_h,
        }
        items.append(item)

    print(f"  Accepted: {len(items)}")
    if skipped_vendor:
        print(f"  Skipped (wrong vendor): {skipped_vendor}")
    if skipped_excluded:
        print(f"  Skipped (non-seating): {skipped_excluded}")
    if skipped_no_image:
        print(f"  Skipped (no image): {skipped_no_image}")
    if skipped_no_price:
        print(f"  Skipped (no price): {skipped_no_price}")

    return items


# ─── Deduplication ────────────────────────────────────────────────────────────

def deduplicate_products(all_products: list[dict]) -> list[dict]:
    """Deduplicate products across stores using name similarity.

    Strategy: Two products are considered duplicates only if they have
    the SAME furniture type AND their collection names are similar (>=0.75).
    This prevents false merges like "Cosmo Swivel Chair" with "Kora Swivel Chair".

    When duplicates are found, prefer the entry with the larger product image.
    """
    print(f"\n=== Deduplicating {len(all_products)} total products ===")

    # Group by (collection_key, type) where collection_key uses similarity matching
    # Each group key is (normalized_collection, type)
    groups: list[tuple[str, str, list[dict]]] = []  # (collection_norm, type, products)

    for product in all_products:
        norm = normalize_for_dedup(product['name'], product['type'])
        # Split into collection part and type part
        parts = norm.split('|', 1)
        collection_norm = parts[0]
        type_norm = parts[1] if len(parts) > 1 else ''

        # Find a matching group: same type AND similar collection name
        matched_idx = None
        for idx, (grp_coll, grp_type, grp_items) in enumerate(groups):
            if grp_type != type_norm:
                continue
            # For very short collection names (1-4 chars), require exact match
            if len(collection_norm) <= 4 or len(grp_coll) <= 4:
                if collection_norm == grp_coll:
                    matched_idx = idx
                    break
            else:
                if similar(collection_norm, grp_coll) >= 0.75:
                    matched_idx = idx
                    break

        if matched_idx is not None:
            groups[matched_idx][2].append(product)
        else:
            groups.append((collection_norm, type_norm, [product]))

    # From each group, pick the best entry (largest image)
    final = []
    duplicates_removed = 0

    for collection_norm, type_norm, group in groups:
        if len(group) > 1:
            # Sort by image area descending, pick largest
            group.sort(key=lambda p: p.get('_image_area', 0), reverse=True)
            winner = group[0]
            losers = group[1:]
            store_list = ', '.join(f"{p['_store']}" for p in group)
            print(f"  DUP: \"{winner['name']}\" found at [{store_list}] "
                  f"-> keeping {winner['_store']} "
                  f"({winner.get('_image_width', '?')}x{winner.get('_image_height', '?')})")
            duplicates_removed += len(losers)
            final.append(winner)
        else:
            final.append(group[0])

    print(f"  Duplicates removed: {duplicates_removed}")
    print(f"  Unique products: {len(final)}")
    return final


# ─── Image Validation ────────────────────────────────────────────────────────

def validate_images(client: httpx.Client, products: list[dict]) -> list[dict]:
    """Validate image URLs and remove products with broken images."""
    print(f"\n=== Validating {len(products)} image URLs ===")

    valid = []
    invalid = 0

    for i, product in enumerate(products):
        url = product['image_url']
        is_valid = validate_image_url(client, url)
        if is_valid:
            valid.append(product)
        else:
            print(f"  INVALID IMAGE: {product['name']} -> {url[:80]}...")
            invalid += 1

        # Progress indicator every 10 items
        if (i + 1) % 10 == 0:
            print(f"  Validated {i + 1}/{len(products)}...")

    print(f"  Valid: {len(valid)}, Invalid: {invalid}")
    return valid


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Jonathan Louis Catalog Scraper")
    print("=" * 60)

    # Create HTTP client with proper headers
    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30)

    try:
        # Step 1: Fetch from all stores
        all_products = []
        store_counts = {}

        for store in STORES:
            products = fetch_store_products(client, store)
            store_counts[store['name']] = len(products)
            all_products.extend(products)
            time.sleep(0.5)  # Be polite between stores

        print(f"\n  Total raw products: {len(all_products)}")
        for store_name, count in store_counts.items():
            print(f"    {store_name}: {count}")

        if not all_products:
            print("ERROR: No products fetched from any store!")
            sys.exit(1)

        # Step 2: Deduplicate across stores
        unique_products = deduplicate_products(all_products)

        # Step 3: Validate image URLs
        validated_products = validate_images(client, unique_products)

        # Step 4: Clean internal metadata and sort
        for product in validated_products:
            product.pop('_store', None)
            product.pop('_image_area', None)
            product.pop('_image_width', None)
            product.pop('_image_height', None)

        # Sort by type, then by name
        type_order = {
            'Sectional': 0, 'Sofa': 1, 'Loveseat': 2, 'Chaise': 3,
            'Chair': 4, 'Swivel Chair': 5, 'Ottoman': 6,
        }
        validated_products.sort(key=lambda p: (type_order.get(p['type'], 99), p['name']))

        # Step 5: Save
        output_path = os.path.abspath(OUTPUT_FILE)

        # Load existing for comparison
        existing_count = 0
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                existing_count = len(existing)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(validated_products, f, indent=2, ensure_ascii=False)

        # Step 6: Summary
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Stores scraped: {len(STORES)}")
        for store_name, count in store_counts.items():
            print(f"    {store_name}: {count} products")
        print(f"  Total raw: {len(all_products)}")
        print(f"  After dedup: {len(unique_products)}")
        print(f"  After image validation: {len(validated_products)}")
        print(f"  Previous catalog: {existing_count} items")
        print(f"  New catalog: {len(validated_products)} items ({len(validated_products) - existing_count:+d})")
        print(f"  Saved to: {output_path}")

        # Type breakdown
        print(f"\n  Type breakdown:")
        type_counts: dict[str, int] = {}
        for p in validated_products:
            t = p['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        for t in sorted(type_counts, key=lambda x: type_order.get(x, 99)):
            print(f"    {t}: {type_counts[t]}")

    finally:
        client.close()


if __name__ == '__main__':
    main()
