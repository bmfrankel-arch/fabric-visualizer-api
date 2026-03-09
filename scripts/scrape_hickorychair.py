"""
Hickory Chair furniture catalog scraper.
Fetches all products from the single-page category listing,
filters to upholstered seating, validates images, deduplicates,
and outputs a unified catalog JSON.

Usage:
    python scrape_hickorychair.py
"""

import json
import os
import random
import re
import sys
import time

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import httpx
from bs4 import BeautifulSoup

# --- Configuration ----------------------------------------------------------------

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'app')
OUTPUT_FILE = os.path.join(BACKEND_DIR, 'hickorychair_catalog.json')

CATEGORY_URL = 'https://hickorychair.com/Products/ShowResults?CategoryID=1'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# --- Type Classification ----------------------------------------------------------

# Furniture types we want (upholstered seating), ordered most specific first
TYPE_KEYWORDS = [
    ('swivel recliner', 'Recliner'),
    ('recliner', 'Recliner'),
    ('reclining', 'Recliner'),
    ('swivel chair', 'Swivel Chair'),
    ('swivel', 'Swivel Chair'),
    ('accent chair', 'Chair'),
    ('arm chair', 'Chair'),
    ('armchair', 'Chair'),
    ('wing chair', 'Chair'),
    ('club chair', 'Chair'),
    ('lounge chair', 'Chair'),
    ('host chair', 'Chair'),
    ('side chair', 'Chair'),
    ('dining chair', 'Chair'),
    ('slipper chair', 'Chair'),
    ('barrel chair', 'Chair'),
    ('chair', 'Chair'),
    ('settee', 'Settee'),
    ('loveseat', 'Loveseat'),
    ('love seat', 'Loveseat'),
    ('sectional', 'Sectional'),
    ('chaise', 'Chaise'),
    ('daybed', 'Chaise'),
    ('ottoman', 'Ottoman'),
    ('footrest', 'Ottoman'),
    ('bench', 'Bench'),
    ('banquette', 'Bench'),
    ('sofa', 'Sofa'),
    ('couch', 'Sofa'),
    ('divan', 'Sofa'),
]

# Keywords that EXCLUDE an item (non-seating furniture)
EXCLUDE_KEYWORDS = [
    'table', 'desk', 'mirror', 'shelf', 'bookcase', 'cabinet', 'chest',
    'nightstand', 'bed', 'headboard', 'lamp', 'chandelier', 'sconce',
    'rug', 'pillow', 'throw', 'screen', 'credenza', 'console', 'etagere',
    'buffet', 'sideboard', 'armoire', 'dresser', 'commode', 'pedestal',
    'bracket', 'finial', 'knob', 'pull', 'hardware',
]

# Words to strip when extracting collection name
TYPE_WORDS = {
    'sofa', 'sectional', 'chair', 'swivel', 'accent', 'arm', 'armchair',
    'chaise', 'ottoman', 'loveseat', 'settee', 'couch', 'bench', 'recliner',
    'reclining', 'wing', 'club', 'lounge', 'host', 'side', 'dining',
    'slipper', 'barrel', 'banquette', 'daybed', 'divan', 'footrest', 'love',
    'left', 'right', 'armless', 'corner', 'wedge', 'bumper', 'return',
    'with', 'and', 'the', 'in', 'w', 'w/', 'pc', 'plus', 'standard',
    'oversized', 'large', 'small', 'medium', 'tight', 'loose', 'back',
    'seat', 'cushion', 'upholstered', 'tufted', 'nailhead', 'skirted',
    'no', 'skirt',
    # Positional / config terms (LAF = Left Arm Facing, etc.)
    'laf', 'raf', 'lsf', 'rsf',
    # Style descriptors that aren't part of the collection name
    'curved', 'button', 'round', 'square', 'high', 'low', 'open',
    'sleeper', 'storage', 'drop-in', 'spring', 'down', 'full',
    'twin', 'queen', 'king', 'tall', 'short', 'deep', 'narrow',
    'wide', 'slim', 'flat', 'plain', 'panel', 'channel',
    'stationary', 'glider', 'rocker', 'swiveling',
    # Made-to-measure / custom suffixes
    'm2m',
    # Unit / piece descriptors
    'unit',
}


# --- Helpers ----------------------------------------------------------------------

def classify_type(name: str) -> str | None:
    """Determine furniture type from product name. Returns None if not seating."""
    lower = name.lower()

    # First check exclusions
    for kw in EXCLUDE_KEYWORDS:
        # Match as whole word to avoid false positives (e.g., 'armchair' containing 'chair')
        if re.search(r'\b' + re.escape(kw) + r'\b', lower):
            return None

    # Then check type keywords
    for keyword, ftype in TYPE_KEYWORDS:
        if re.search(r'\b' + re.escape(keyword) + r'\b', lower):
            return ftype

    return None  # Not recognized as seating


def extract_collection(name: str) -> str:
    """Extract collection name from product name.

    Strategy: take words from the start until we hit a type/descriptor keyword.
    e.g. "5th Avenue Armless Chair" -> "5th Avenue"
         "Wilshire Tufted Sofa" -> "Wilshire"
         "Marin Left Arm Chaise" -> "Marin"
    """
    # Remove parenthetical notes
    cleaned = re.sub(r'\(.*?\)', '', name).strip()
    # Remove piece indicators
    cleaned = re.sub(r'\d+[-\s]?piece', '', cleaned, flags=re.IGNORECASE).strip()

    words = cleaned.split()
    collection_words = []

    for w in words:
        w_lower = w.lower().rstrip('.,;')
        # Stop at type or descriptor keywords
        if w_lower in TYPE_WORDS or w_lower.rstrip('s') in TYPE_WORDS:
            break
        collection_words.append(w)

    result = ' '.join(collection_words).strip()

    # If empty (e.g., name starts with a type word), use first word
    if not result and words:
        result = words[0]

    return result


def validate_image_url(client: httpx.Client, url: str) -> bool:
    """Validate that an image URL returns a successful response with image content-type."""
    if not url:
        return False
    try:
        resp = client.head(url, follow_redirects=True, timeout=10)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get('content-type', '')
        # Accept image types or octet-stream (some CDNs)
        return 'image' in content_type or 'octet-stream' in content_type
    except (httpx.HTTPError, httpx.TimeoutException):
        # Fall back to GET if HEAD fails
        try:
            resp = client.get(url, follow_redirects=True, timeout=10)
            if resp.status_code != 200:
                return False
            content_type = resp.headers.get('content-type', '')
            return 'image' in content_type or 'octet-stream' in content_type
        except (httpx.HTTPError, httpx.TimeoutException):
            return False


# --- Scraper ----------------------------------------------------------------------

def fetch_and_parse(client: httpx.Client) -> list[dict]:
    """Fetch the category page and parse all product items."""
    print(f"\nFetching: {CATEGORY_URL}")

    resp = client.get(CATEGORY_URL, timeout=60)
    resp.raise_for_status()

    html = resp.text
    print(f"  Page size: {len(html):,} bytes")

    soup = BeautifulSoup(html, 'html.parser')
    search_items = soup.select('div.search-item')
    print(f"  Found {len(search_items)} .search-item elements")

    products = []
    skipped_no_link = 0
    skipped_no_image = 0
    skipped_excluded = 0
    skipped_no_type = 0

    for item in search_items:
        # Find the link
        link = item.find('a')
        if not link or not link.get('href'):
            skipped_no_link += 1
            continue

        href = link['href']

        # Extract SKU
        sku_div = item.select_one('.search-item-sku')
        sku = sku_div.get_text(strip=True) if sku_div else ''

        # Extract name
        name_div = item.select_one('.search-item-name')
        name = name_div.get_text(strip=True) if name_div else ''

        if not name:
            # Try the alt text from the image
            img = item.find('img')
            if img and img.get('alt'):
                name = img['alt'].strip()

        if not name and not sku:
            skipped_no_link += 1
            continue

        # Use SKU as fallback name
        if not name:
            name = sku

        # Clean up whitespace in name (collapse multiple spaces)
        name = re.sub(r'\s+', ' ', name).strip()

        # Extract image
        img = item.find('img')
        if not img or not img.get('src'):
            skipped_no_image += 1
            continue

        img_src = img['src']

        # Build full image URL
        if img_src.startswith('/'):
            img_src = 'https://hickorychair.com' + img_src

        # Build hires variant
        img_hires = img_src.replace('_medium.jpg', '_hires.jpg')
        img_medium = img_src  # keep medium as fallback

        # Build product URL
        if href.startswith('/'):
            product_url = 'https://hickorychair.com' + href
        else:
            product_url = href

        # Extract SKU from URL if not found in DOM
        if not sku:
            match = re.search(r'/ProductDetails/([^/?]+)', href)
            if match:
                sku = match.group(1)

        # Classify type
        ftype = classify_type(name)
        if ftype is None:
            skipped_excluded += 1
            continue

        # Extract collection
        collection = extract_collection(name)

        # Extract image filename for dedup
        img_filename = os.path.basename(img_src).split('?')[0]
        # Normalize to medium for dedup comparison
        img_filename_norm = img_filename.replace('_hires.jpg', '_medium.jpg')

        products.append({
            'name': name,
            'sku': sku,
            'price': 0,
            'compare_at_price': 0,
            'on_sale': False,
            'collection': collection,
            'color': 'As Shown',
            'url': product_url,
            'image_url_hires': img_hires,
            'image_url_medium': img_medium,
            'image_url': img_medium,  # will be finalized after validation
            'category': 'Living',
            'type': ftype,
            'brand': 'Hickory Chair',
            'material': 'Fabric',
            '_img_filename': img_filename_norm,
        })

    print(f"\n  Parsed products (seating): {len(products)}")
    if skipped_no_link:
        print(f"  Skipped (no link): {skipped_no_link}")
    if skipped_no_image:
        print(f"  Skipped (no image): {skipped_no_image}")
    if skipped_excluded:
        print(f"  Skipped (non-seating): {skipped_excluded}")

    return products


# --- Deduplication ----------------------------------------------------------------

def deduplicate_by_image(products: list[dict]) -> list[dict]:
    """Deduplicate by image filename.

    Multiple SKUs may share the same image for sectional pieces.
    Keep the first occurrence (usually the main product).
    """
    print(f"\n=== Deduplicating {len(products)} products by image filename ===")

    seen: dict[str, dict] = {}
    duplicates = 0

    for p in products:
        key = p['_img_filename']
        if key in seen:
            existing = seen[key]
            # Prefer the one with a more descriptive name (longer name)
            if len(p['name']) > len(existing['name']):
                seen[key] = p
            duplicates += 1
        else:
            seen[key] = p

    result = list(seen.values())
    print(f"  Duplicates removed: {duplicates}")
    print(f"  Unique products: {len(result)}")
    return result


# --- Image Validation (sample) ---------------------------------------------------

def validate_and_choose_images(client: httpx.Client, products: list[dict]) -> list[dict]:
    """Validate a sample of hires URLs. If hires works, use it for all; else fall back to medium."""
    print(f"\n=== Validating image URLs (sampling 20 random products) ===")

    if not products:
        return products

    # Sample 20 random products to test hires availability
    sample_size = min(20, len(products))
    sample = random.sample(products, sample_size)

    hires_valid = 0
    hires_invalid = 0
    medium_valid = 0
    medium_invalid = 0

    for p in sample:
        # Test hires
        hires_ok = validate_image_url(client, p['image_url_hires'])
        if hires_ok:
            hires_valid += 1
        else:
            hires_invalid += 1

        # Test medium
        medium_ok = validate_image_url(client, p['image_url_medium'])
        if medium_ok:
            medium_valid += 1
        else:
            medium_invalid += 1

        time.sleep(0.1)  # Be polite

    print(f"  Hires sample: {hires_valid}/{sample_size} valid ({hires_valid/sample_size*100:.0f}%)")
    print(f"  Medium sample: {medium_valid}/{sample_size} valid ({medium_valid/sample_size*100:.0f}%)")

    # Decision: if hires works for most samples, use hires; otherwise use medium
    use_hires = (hires_valid / sample_size) >= 0.8
    chosen_key = 'image_url_hires' if use_hires else 'image_url_medium'
    print(f"  Decision: using {'hires' if use_hires else 'medium'} URLs")

    # Set final image_url
    for p in products:
        p['image_url'] = p[chosen_key]

    # Now validate ALL image URLs with the chosen resolution
    print(f"\n  Validating all {len(products)} {('hires' if use_hires else 'medium')} image URLs...")
    valid_products = []
    invalid_count = 0

    for i, p in enumerate(products):
        ok = validate_image_url(client, p['image_url'])
        if ok:
            valid_products.append(p)
        else:
            # If hires failed, try medium as fallback
            if use_hires:
                ok2 = validate_image_url(client, p['image_url_medium'])
                if ok2:
                    p['image_url'] = p['image_url_medium']
                    valid_products.append(p)
                else:
                    print(f"  INVALID: {p['name']} ({p['sku']})")
                    invalid_count += 1
            else:
                print(f"  INVALID: {p['name']} ({p['sku']})")
                invalid_count += 1

        if (i + 1) % 50 == 0:
            print(f"    Validated {i + 1}/{len(products)}...")

        time.sleep(0.05)  # Be polite

    print(f"  Valid: {len(valid_products)}, Invalid: {invalid_count}")
    return valid_products


# --- Main -------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Hickory Chair Catalog Scraper")
    print("=" * 60)

    client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60)

    try:
        # Step 1: Fetch and parse the category page
        products = fetch_and_parse(client)

        if not products:
            print("ERROR: No products found!")
            sys.exit(1)

        # Step 2: Deduplicate by image filename
        products = deduplicate_by_image(products)

        # Step 3: Validate images and choose hires vs medium
        products = validate_and_choose_images(client, products)

        if not products:
            print("ERROR: No valid products after image validation!")
            sys.exit(1)

        # Step 4: Clean internal metadata
        for p in products:
            p.pop('_img_filename', None)
            p.pop('image_url_hires', None)
            p.pop('image_url_medium', None)

        # Step 5: Sort by type then name
        type_order = {
            'Sectional': 0, 'Sofa': 1, 'Loveseat': 2, 'Settee': 3,
            'Chaise': 4, 'Chair': 5, 'Swivel Chair': 6, 'Recliner': 7,
            'Ottoman': 8, 'Bench': 9,
        }
        products.sort(key=lambda p: (type_order.get(p['type'], 99), p['name']))

        # Step 6: Save
        output_path = os.path.abspath(OUTPUT_FILE)

        # Load existing for comparison
        existing_count = 0
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                existing_count = len(existing)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(products, f, indent=2, ensure_ascii=False)

        # Step 7: Summary
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Total products on page: (see parse step above)")
        print(f"  After type filter (seating only): (see parse step above)")
        print(f"  After dedup: (see dedup step above)")
        print(f"  After image validation: {len(products)}")
        print(f"  Previous catalog: {existing_count} items")
        print(f"  New catalog: {len(products)} items")
        print(f"  Saved to: {output_path}")

        # Type breakdown
        print(f"\n  Type breakdown:")
        type_counts: dict[str, int] = {}
        for p in products:
            t = p['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        for t in sorted(type_counts, key=lambda x: type_order.get(x, 99)):
            print(f"    {t:15s}: {type_counts[t]:>4d}")
        print(f"    {'TOTAL':15s}: {len(products):>4d}")

        # Sample entries
        print(f"\n  Sample entries:")
        for p in products[:5]:
            print(f"    {p['sku']:15s} | {p['type']:12s} | {p['collection']:20s} | {p['name']}")

    finally:
        client.close()


if __name__ == '__main__':
    main()
