#!/usr/bin/env python3
"""
CR Laine Catalog Scraper
========================
Scrapes the CR Laine website category pages to build a furniture catalog
for the Dorell fabric visualizer app.

CR Laine is a trade-only upholstered furniture manufacturer. The site serves
server-rendered HTML with product links containing productDetail in the href.

Usage:
    python scripts/scrape_crlaine.py

The script:
1. Fetches each category page (Sofas, Loveseats, Sectionals, Chairs, Swivels, Ottomans)
2. Parses product links with BeautifulSoup
3. Extracts style name, style number, product ID from href paths
4. Excludes leather variants (style numbers starting with "L")
5. Builds image URLs from style numbers (xlarge or thumbnail fallback)
6. Validates a sample of image URLs to pick the best size
7. Deduplicates by style number
8. Saves sorted catalog to backend/app/crlaine_catalog.json
"""

import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 is required. Install with: pip install beautifulsoup4")
    sys.exit(1)


# --- Configuration ---
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CATALOG_FILE = PROJECT_DIR / "backend" / "app" / "crlaine_catalog.json"

BASE_URL = "https://www.crlaine.com"
AZURE_BACKEND = "https://rff-portal-prod.azurewebsites.net"

# Category pages to scrape: (url_path, furniture_type)
CATEGORIES = [
    ("/products/CRL/cat/4/category/Sofas", "Sofa"),
    ("/products/CRL/cat/5/category/Loveseats", "Loveseat"),
    ("/products/CRL/cat/6/category/Sectionals", "Sectional"),
    ("/products/CRL/cat/7/category/Chairs", "Chair"),
    ("/products/CRL/cat/8/category/Swivels", "Swivel Chair"),
    ("/products/CRL/cat/11/category/Ottomans", "Ottoman"),
]

# Image URL patterns
IMAGE_XLARGE = "{base}/assets/images/products/xlarge/{style_number}.jpg"
IMAGE_THUMBNAIL = "{base}/assets/images/products/thumbnails/{style_number}.jpg"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

MAX_CONCURRENT = 8
BATCH_DELAY = 0.3


def parse_product_links(html: str, furniture_type: str, base_url: str) -> list[dict]:
    """Parse product links from a category page HTML.

    Each product link looks like:
      <a href="/productDetail/CRL/id/{productID}/styleName/{styleName}/styleNumber/{styleNumber}">
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_numbers = set()

    # Find all links with productDetail in href
    links = soup.find_all("a", href=re.compile(r"productDetail"))

    for link in links:
        href = link.get("href", "")

        # Extract fields from the URL path
        # Pattern: /productDetail/CRL/id/{id}/styleName/{name}/styleNumber/{number}
        id_match = re.search(r"/id/(\d+)", href)
        name_match = re.search(r"/styleName/([^/]+)", href)
        number_match = re.search(r"/styleNumber/([^/]+)", href)

        if not (id_match and name_match and number_match):
            continue

        product_id = id_match.group(1)
        style_name = unquote(name_match.group(1)).strip()
        style_number = unquote(number_match.group(1)).strip()

        # Skip leather variants (style numbers starting with "L")
        if style_number.upper().startswith("L"):
            continue

        # Deduplicate by style number within this parse
        if style_number in seen_numbers:
            continue
        seen_numbers.add(style_number)

        # Clean up style name - replace URL encoding artifacts
        style_name = style_name.replace("%20", " ").replace("+", " ")
        # Title-case the style name
        style_name = style_name.title()

        # Build the product detail URL
        product_url = f"{base_url}/productDetail/CRL/id/{product_id}/styleName/{style_name}/styleNumber/{style_number}"

        products.append({
            "product_id": product_id,
            "style_name": style_name,
            "style_number": style_number,
            "type": furniture_type,
            "url": product_url,
        })

    return products


async def fetch_category_page(
    client: httpx.AsyncClient,
    url_path: str,
    furniture_type: str,
    base_url: str,
) -> list[dict]:
    """Fetch a single category page and parse products."""
    url = f"{base_url}{url_path}"
    print(f"  Fetching {furniture_type}: {url}")

    try:
        response = await client.get(url, follow_redirects=True, timeout=30.0)

        # Check if we got redirected away from crlaine.com
        final_url = str(response.url)
        if "crlaine.com" not in final_url and base_url == BASE_URL:
            print(f"    WARNING: Redirected to {final_url}")
            print(f"    Trying Azure backend...")
            url = f"{AZURE_BACKEND}{url_path}"
            response = await client.get(url, follow_redirects=True, timeout=30.0)
            final_url = str(response.url)

        if response.status_code != 200:
            print(f"    ERROR: HTTP {response.status_code}")
            return []

        products = parse_product_links(response.text, furniture_type, base_url)
        print(f"    Found {len(products)} products")
        return products

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        print(f"    ERROR: {e}")
        # Try Azure fallback
        if base_url == BASE_URL:
            print(f"    Trying Azure backend...")
            return await fetch_category_page(client, url_path, furniture_type, AZURE_BACKEND)
        return []


async def validate_image_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool]:
    """Validate an image URL. Returns (url, is_valid)."""
    async with semaphore:
        try:
            response = await client.head(url, follow_redirects=True, timeout=10.0)
            content_type = response.headers.get("content-type", "")
            is_valid = response.status_code == 200 and (
                "image" in content_type or content_type == ""
            )
            return url, is_valid
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return url, False


async def determine_image_size(
    client: httpx.AsyncClient,
    style_numbers: list[str],
    base_url: str,
) -> str:
    """Test a sample of image URLs to determine which size works (xlarge vs thumbnail).

    Returns 'xlarge' or 'thumbnails'.
    """
    if not style_numbers:
        return "xlarge"

    # Pick up to 20 random style numbers to test
    sample_size = min(20, len(style_numbers))
    sample = random.sample(style_numbers, sample_size)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # Test xlarge URLs
    xlarge_urls = [
        IMAGE_XLARGE.format(base=base_url, style_number=sn) for sn in sample
    ]

    tasks = [validate_image_url(client, url, semaphore) for url in xlarge_urls]
    results = await asyncio.gather(*tasks)
    xlarge_valid = sum(1 for _, valid in results if valid)

    print(f"  XLarge image validation: {xlarge_valid}/{sample_size} valid")

    if xlarge_valid >= sample_size * 0.5:
        print(f"  Using xlarge images (majority valid)")
        return "xlarge"

    # Test thumbnail URLs
    thumb_urls = [
        IMAGE_THUMBNAIL.format(base=base_url, style_number=sn) for sn in sample
    ]

    tasks = [validate_image_url(client, url, semaphore) for url in thumb_urls]
    results = await asyncio.gather(*tasks)
    thumb_valid = sum(1 for _, valid in results if valid)

    print(f"  Thumbnail image validation: {thumb_valid}/{sample_size} valid")

    if thumb_valid > xlarge_valid:
        print(f"  Using thumbnail images (more valid than xlarge)")
        return "thumbnails"

    # Default to xlarge even if both are poor - user can troubleshoot
    print(f"  Defaulting to xlarge images")
    return "xlarge"


async def validate_all_images(
    client: httpx.AsyncClient,
    entries: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Validate image URLs for all entries. Returns (valid, invalid)."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    valid = []
    invalid = []
    total = len(entries)

    batch_size = MAX_CONCURRENT * 2
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = entries[batch_start:batch_end]

        tasks = [
            validate_image_url(client, entry["image_url"], semaphore)
            for entry in batch
        ]
        results = await asyncio.gather(*tasks)

        for entry, (_, is_valid) in zip(batch, results):
            if is_valid:
                valid.append(entry)
            else:
                invalid.append(entry)

        done = batch_end
        print(
            f"  Validated {done}/{total} images "
            f"({len(valid)} valid, {len(invalid)} invalid)",
            end="\r",
        )

        if batch_end < total:
            await asyncio.sleep(BATCH_DELAY)

    print()  # newline after progress
    return valid, invalid


def build_catalog_entry(
    product: dict,
    image_size: str,
    base_url: str,
) -> dict:
    """Build a catalog entry from parsed product data."""
    style_name = product["style_name"]
    style_number = product["style_number"]
    furniture_type = product["type"]

    if image_size == "xlarge":
        image_url = IMAGE_XLARGE.format(base=base_url, style_number=style_number)
    else:
        image_url = IMAGE_THUMBNAIL.format(base=base_url, style_number=style_number)

    return {
        "name": f"{style_name} {furniture_type}",
        "sku": style_number,
        "price": 0,
        "compare_at_price": 0,
        "on_sale": False,
        "collection": style_name,
        "color": "As Shown",
        "url": product["url"],
        "image_url": image_url,
        "category": "Living",
        "type": furniture_type,
        "brand": "CR Laine",
        "material": "Fabric",
    }


async def main():
    print("=" * 60)
    print("CR Laine Catalog Scraper")
    print("=" * 60)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    all_products = []
    base_url = BASE_URL

    async with httpx.AsyncClient(headers=headers) as client:

        # Step 1: Fetch all category pages
        print(f"\n[1/5] Fetching category pages from {base_url}...")
        for url_path, furniture_type in CATEGORIES:
            products = await fetch_category_page(client, url_path, furniture_type, base_url)

            # If the main site redirected or failed, update base_url for subsequent requests
            if not products and base_url == BASE_URL:
                print(f"  Main site failed for {furniture_type}, trying Azure backend...")
                products = await fetch_category_page(
                    client, url_path, furniture_type, AZURE_BACKEND
                )
                if products:
                    base_url = AZURE_BACKEND
                    print(f"  Switched to Azure backend for remaining requests")

            all_products.extend(products)
            await asyncio.sleep(0.5)  # polite delay between categories

        print(f"\n  Total raw products scraped: {len(all_products)}")

        # Step 2: Deduplicate by style number (across categories)
        print(f"\n[2/5] Deduplicating by style number...")
        seen = {}
        for product in all_products:
            sn = product["style_number"]
            if sn not in seen:
                seen[sn] = product
            # If duplicate, keep the first occurrence (it has the correct type)

        unique_products = list(seen.values())
        dupes_removed = len(all_products) - len(unique_products)
        print(f"  Unique products: {len(unique_products)} (removed {dupes_removed} duplicates)")

        # Step 3: Determine best image size
        print(f"\n[3/5] Testing image URL sizes...")
        style_numbers = [p["style_number"] for p in unique_products]
        image_size = await determine_image_size(client, style_numbers, base_url)

        # Step 4: Build catalog entries
        print(f"\n[4/5] Building catalog entries...")
        entries = [
            build_catalog_entry(p, image_size, base_url)
            for p in unique_products
        ]

        # Validate all image URLs
        print(f"  Validating {len(entries)} image URLs...")
        start_time = time.time()
        valid_entries, invalid_entries = await validate_all_images(client, entries)
        elapsed = time.time() - start_time
        print(f"  Validation complete in {elapsed:.1f}s")
        print(f"  Valid: {len(valid_entries)}, Invalid: {len(invalid_entries)}")

        # If many xlarge failed, retry invalid ones with thumbnail
        if invalid_entries and image_size == "xlarge":
            print(f"\n  Retrying {len(invalid_entries)} failed items with thumbnail URLs...")
            for entry in invalid_entries:
                sn = entry["sku"]
                entry["image_url"] = IMAGE_THUMBNAIL.format(
                    base=base_url, style_number=sn
                )

            retry_valid, retry_invalid = await validate_all_images(client, invalid_entries)
            print(f"  Thumbnail retry: {len(retry_valid)} recovered, {len(retry_invalid)} still invalid")

            valid_entries.extend(retry_valid)
            invalid_entries = retry_invalid

    # Step 5: Sort and save
    print(f"\n[5/5] Sorting and saving catalog...")

    # Sort by type then name
    type_order = {
        "Sofa": 0,
        "Loveseat": 1,
        "Sectional": 2,
        "Chair": 3,
        "Swivel Chair": 4,
        "Ottoman": 5,
    }
    valid_entries.sort(key=lambda e: (type_order.get(e["type"], 99), e["name"]))

    # Save
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(valid_entries, f, indent=2, ensure_ascii=False)

    print(f"  Saved {len(valid_entries)} entries to {CATALOG_FILE}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Raw products scraped:    {len(all_products)}")
    print(f"  After dedup:             {len(unique_products)}")
    print(f"  Valid images:            {len(valid_entries)}")
    print(f"  Invalid images:          {len(invalid_entries)}")
    print(f"  Image size used:         {image_size}")
    print(f"  Final catalog size:      {len(valid_entries)}")

    if invalid_entries:
        print(f"\n  Invalid image SKUs (first 15):")
        for entry in invalid_entries[:15]:
            print(f"    - {entry['sku']}: {entry['name']}")

    # Type breakdown
    print("\nType breakdown:")
    type_counts = {}
    for entry in valid_entries:
        t = entry["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")

    print("=" * 60)
    return len(valid_entries)


if __name__ == "__main__":
    count = asyncio.run(main())
    print(f"\nDone. {count} items in catalog.")
