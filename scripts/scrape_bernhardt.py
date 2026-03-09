#!/usr/bin/env python3
"""
Bernhardt Catalog Builder
=========================
Reads scraped product data from bernhardt_scraped.json (extracted from bernhardt.com),
validates S3 image URLs with HEAD requests, builds catalog entries matching the
existing bernhardt_catalog.json schema, and merges with the existing catalog.

Usage:
    python scripts/scrape_bernhardt.py

The script:
1. Loads scraped product data (names, SKUs, brands, types) from bernhardt_scraped.json
2. Constructs S3 image URLs using the pattern:
   https://s3.amazonaws.com/emuncloud-staticassets/productImages/bh074/large/{SKU}.jpg
3. Validates each image URL with a HEAD request (concurrent, rate-limited)
4. Builds catalog entries in the standard JSON structure
5. Merges with the existing bernhardt_catalog.json, avoiding SKU duplicates
6. Saves the final catalog to bernhardt_catalog.json
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)


# --- Configuration ---
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
SCRAPED_DATA_FILE = SCRIPT_DIR / "bernhardt_scraped.json"
CATALOG_FILE = PROJECT_DIR / "backend" / "app" / "bernhardt_catalog.json"

S3_IMAGE_BASE = "https://s3.amazonaws.com/emuncloud-staticassets/productImages/bh074/large"
PRODUCT_URL_BASE = "https://www.bernhardt.com/shop"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Rate limiting: max concurrent HEAD requests
MAX_CONCURRENT = 8
# Delay between batches (seconds)
BATCH_DELAY = 0.3


# --- Brand mapping ---
BRAND_MAP = {
    "Bernhardt Living": "Bernhardt",
    "Bernhardt Interiors": "Bernhardt",
    "Bernhardt Loft": "Bernhardt",
    "Bernhardt": "Bernhardt",
}

SUB_BRAND_MAP = {
    "Bernhardt Living": "Bernhardt Living",
    "Bernhardt Interiors": "Bernhardt Interiors",
    "Bernhardt Loft": "Bernhardt Loft",
    "Bernhardt": "Bernhardt",
}


def extract_collection(name: str) -> str:
    """Extract collection name from product name.

    The collection is typically the first word of the product name.
    E.g., 'Addison Fabric Sofa' -> 'Addison'
          'Germain Cream Power Reclining Sofa' -> 'Germain'
    """
    if not name:
        return "Unknown"
    # Take the first word as collection name
    first_word = name.split()[0] if name.split() else "Unknown"
    return first_word


def determine_type(name: str, scraped_type: str, category: str) -> str:
    """Determine the furniture type from name, scraped type, and category."""
    name_lower = name.lower()

    # Check name for specific type keywords
    if "loveseat" in name_lower:
        return "Loveseat"
    if "sectional" in name_lower:
        return "Sectional"
    if "chaise" in name_lower:
        return "Chaise"
    if "ottoman" in name_lower:
        return "Ottoman"
    if "bench" in name_lower:
        return "Bench"
    if "recliner" in name_lower:
        return "Recliner"
    if "swivel" in name_lower:
        return "Chair"

    # Use scraped type
    if scraped_type in ("Sofa", "Chair", "Loveseat", "Sectional", "Ottoman", "Bench", "Chaise"):
        return scraped_type

    # Fall back to category
    return category if category in ("Sofa", "Chair") else "Sofa"


def determine_configuration(name: str, furniture_type: str) -> str:
    """Determine configuration from the product name and type."""
    name_lower = name.lower()

    if "power reclining" in name_lower:
        return "Power Reclining"
    if "reclining" in name_lower:
        return "Reclining"
    if "swivel" in name_lower:
        return "Swivel"

    # Check for piece count in name
    piece_match = re.search(r"(\d+)[- ]piece", name_lower)
    if piece_match:
        return f"{piece_match.group(1)}-Piece"

    if furniture_type == "Sofa":
        return "3-Seat"
    elif furniture_type == "Loveseat":
        return "2-Seat"
    elif furniture_type == "Chair":
        return "Accent"
    elif furniture_type == "Sectional":
        return "Sectional"
    else:
        return "Stationary"


def determine_pieces(furniture_type: str, name: str) -> int:
    """Determine number of pieces."""
    piece_match = re.search(r"(\d+)[- ]piece", name.lower())
    if piece_match:
        return int(piece_match.group(1))
    return 1


def is_fabric_item(name: str, sku: str) -> bool:
    """Check if item is a fabric item (not leather-only)."""
    name_lower = name.lower()
    # Exclude items that are explicitly leather-only
    # Items with "Leather" in name AND no "Fabric" -> leather only
    if "leather" in name_lower and "fabric" not in name_lower:
        return False
    return True


def build_catalog_entry(item: dict) -> dict:
    """Build a catalog entry from scraped data."""
    name = item["name"]
    sku = item["sku"]
    brand = item.get("brand", "Bernhardt")
    scraped_type = item.get("type", "Sofa")
    category = item.get("category", "Sofa")

    furniture_type = determine_type(name, scraped_type, category)
    collection = extract_collection(name)
    configuration = determine_configuration(name, furniture_type)
    pieces = determine_pieces(furniture_type, name)

    image_url = f"{S3_IMAGE_BASE}/{sku}.jpg"
    product_url = f"{PRODUCT_URL_BASE}/{sku}"

    return {
        "name": name,
        "sku": sku,
        "price": 0.0,
        "compare_at_price": 0.0,
        "on_sale": False,
        "collection": collection,
        "color": "Varies",
        "url": product_url,
        "image_url": image_url,
        "category": "Living",
        "type": furniture_type,
        "brand": "Bernhardt",
        "material": "Fabric",
        "configuration": configuration,
        "pieces": pieces,
    }


async def validate_image_url(client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore) -> bool:
    """Validate an image URL with a HEAD request."""
    async with semaphore:
        try:
            response = await client.head(url, follow_redirects=True, timeout=10.0)
            return response.status_code == 200
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
            return False


async def validate_images(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate image URLs for all entries. Returns (valid, invalid) lists."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }

    valid = []
    invalid = []

    async with httpx.AsyncClient(headers=headers) as client:
        # Process in batches
        batch_size = MAX_CONCURRENT * 2
        total = len(entries)

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = entries[batch_start:batch_end]

            tasks = [
                validate_image_url(client, entry["image_url"], semaphore)
                for entry in batch
            ]

            results = await asyncio.gather(*tasks)

            for entry, is_valid in zip(batch, results):
                if is_valid:
                    valid.append(entry)
                else:
                    invalid.append(entry)

            # Progress
            done = batch_end
            valid_count = len(valid)
            print(
                f"  Validated {done}/{total} images "
                f"({valid_count} valid, {len(invalid)} invalid)",
                end="\r",
            )

            # Rate limiting between batches
            if batch_end < total:
                await asyncio.sleep(BATCH_DELAY)

    print()  # newline after progress
    return valid, invalid


def load_existing_catalog() -> list[dict]:
    """Load the existing bernhardt_catalog.json."""
    if not CATALOG_FILE.exists():
        print(f"  No existing catalog found at {CATALOG_FILE}")
        return []

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"  Loaded {len(data)} existing catalog entries")
    return data


def load_scraped_data() -> list[dict]:
    """Load scraped data from bernhardt_scraped.json."""
    if not SCRAPED_DATA_FILE.exists():
        print(f"ERROR: Scraped data file not found: {SCRAPED_DATA_FILE}")
        sys.exit(1)

    with open(SCRAPED_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"  Loaded {len(data)} scraped products")
    return data


def merge_catalogs(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """Merge new entries with existing catalog, avoiding SKU duplicates.

    Existing entries take priority (they may have manually curated data).
    """
    existing_skus = {entry["sku"] for entry in existing}
    merged = list(existing)  # Start with existing

    added = 0
    for entry in new_entries:
        if entry["sku"] not in existing_skus:
            merged.append(entry)
            existing_skus.add(entry["sku"])
            added += 1

    print(f"  Added {added} new entries (skipped {len(new_entries) - added} duplicates)")
    return merged


def save_catalog(catalog: list[dict]) -> None:
    """Save the catalog to bernhardt_catalog.json."""
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"  Saved {len(catalog)} entries to {CATALOG_FILE}")


async def main():
    print("=" * 60)
    print("Bernhardt Catalog Builder")
    print("=" * 60)

    # Step 1: Load scraped data
    print("\n[1/5] Loading scraped product data...")
    scraped = load_scraped_data()

    # Step 2: Filter to fabric items only and build catalog entries
    print("\n[2/5] Building catalog entries...")
    all_entries = []
    leather_skipped = 0

    for item in scraped:
        if is_fabric_item(item["name"], item["sku"]):
            entry = build_catalog_entry(item)
            all_entries.append(entry)
        else:
            leather_skipped += 1

    print(f"  Built {len(all_entries)} fabric entries (skipped {leather_skipped} leather-only items)")

    # Step 3: Validate image URLs
    print(f"\n[3/5] Validating {len(all_entries)} image URLs (concurrency={MAX_CONCURRENT})...")
    start_time = time.time()
    valid_entries, invalid_entries = await validate_images(all_entries)
    elapsed = time.time() - start_time
    print(f"  Validation complete in {elapsed:.1f}s")
    print(f"  Valid images: {len(valid_entries)}")
    print(f"  Invalid images: {len(invalid_entries)}")

    if invalid_entries:
        print("\n  Invalid image SKUs (first 20):")
        for entry in invalid_entries[:20]:
            print(f"    - {entry['sku']}: {entry['name']}")

    # Step 4: Load existing catalog and merge
    print("\n[4/5] Loading existing catalog and merging...")
    existing = load_existing_catalog()
    merged = merge_catalogs(existing, valid_entries)

    # Step 5: Save
    print("\n[5/5] Saving final catalog...")
    save_catalog(merged)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Scraped products:      {len(scraped)}")
    print(f"  Fabric items:          {len(all_entries)}")
    print(f"  Leather-only skipped:  {leather_skipped}")
    print(f"  Valid images:          {len(valid_entries)}")
    print(f"  Invalid images:        {len(invalid_entries)}")
    print(f"  Existing catalog:      {len(existing)}")
    print(f"  New entries added:     {len(merged) - len(existing)}")
    print(f"  Final catalog size:    {len(merged)}")
    print("=" * 60)

    # Type breakdown
    type_counts = {}
    for entry in merged:
        t = entry.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print("\nType breakdown:")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
