"""
Clean up Rooms To Go catalog:
1. Remove duplicate entries (keep best image variant per name)
2. Try to swap _image-room URLs to _image-item for cleaner product shots
3. Validate all final image URLs
4. Remove items with broken images

Usage:
    python scripts/validate_rtg_images.py
"""

import json
import asyncio
import httpx
from pathlib import Path

CATALOG_PATH = Path(__file__).parent.parent / "backend" / "app" / "roomstogo_catalog.json"


def prefer_image_item(items_with_same_name):
    """Given multiple entries for the same product, pick the best one.
    Prefer _image-item over _image-room over _image-3-2.
    """
    priority = {"_image-item": 0, "_image-3-2": 1, "_image-room": 2}

    def score(item):
        url = item.get("image_url", "")
        for suffix, rank in priority.items():
            if suffix in url:
                return rank
        return 99

    return min(items_with_same_name, key=score)


def deduplicate(items):
    """Keep only one entry per unique name, preferring product shots."""
    by_name = {}
    for item in items:
        name = item["name"]
        if name not in by_name:
            by_name[name] = [item]
        else:
            by_name[name].append(item)

    deduped = []
    for name, group in by_name.items():
        best = prefer_image_item(group)
        deduped.append(best)

    return deduped


async def try_upgrade_to_item(url, client):
    """Try to swap _image-room to _image-item for a cleaner product shot."""
    if "_image-room" not in url:
        return url  # Already a product shot

    # Try _image-item variant
    item_url = url.replace("_image-room", "_image-item")
    # Remove .webp extension if present (some _image-item URLs don't have it)
    for variant in [item_url, item_url.replace(".webp", "")]:
        try:
            resp = await client.head(variant)
            if resp.status_code == 200:
                return variant
        except Exception:
            pass

    # Fallback: keep the room shot
    return url


async def validate_and_clean():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} items from roomstogo_catalog.json")

    # Step 1: Deduplicate
    deduped = deduplicate(items)
    removed_dupes = len(items) - len(deduped)
    print(f"Step 1: Deduplicated — removed {removed_dupes} duplicates, {len(deduped)} unique items remain")

    # Step 2: Try upgrading _image-room to _image-item
    room_count = sum(1 for it in deduped if "_image-room" in it.get("image_url", ""))
    print(f"Step 2: {room_count} items have _image-room URLs, trying to upgrade to _image-item...")

    upgraded = 0
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        sem = asyncio.Semaphore(10)

        async def upgrade(item):
            nonlocal upgraded
            url = item.get("image_url", "")
            if "_image-room" in url:
                async with sem:
                    new_url = await try_upgrade_to_item(url, client)
                    if new_url != url:
                        item["image_url"] = new_url
                        upgraded += 1

        tasks = [upgrade(item) for item in deduped]
        await asyncio.gather(*tasks)

    print(f"  Upgraded {upgraded} of {room_count} room images to product shots")

    # Step 3: Validate all URLs
    print(f"Step 3: Validating all {len(deduped)} image URLs...")
    working = []
    broken = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        sem = asyncio.Semaphore(10)

        async def check(item):
            url = item.get("image_url", "")
            if not url:
                broken.append(item)
                return
            async with sem:
                try:
                    resp = await client.head(url)
                    if resp.status_code == 200:
                        working.append(item)
                    else:
                        broken.append(item)
                        print(f"  BROKEN ({resp.status_code}): {item['name']}")
                except Exception as e:
                    broken.append(item)
                    print(f"  ERROR: {item['name']} — {e}")

        tasks = [check(item) for item in deduped]
        await asyncio.gather(*tasks)

    print(f"  {len(working)} working, {len(broken)} broken")

    # Sort by name
    working.sort(key=lambda x: x.get("name", ""))

    # Save
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(working, f, indent=2)

    # Final summary
    final_room = sum(1 for it in working if "_image-room" in it.get("image_url", ""))
    final_item = sum(1 for it in working if "_image-item" in it.get("image_url", ""))

    print(f"\n=== SUMMARY ===")
    print(f"Original: {len(items)} items")
    print(f"After dedup: {len(deduped)} items (-{removed_dupes} duplicates)")
    print(f"After validation: {len(working)} items (-{len(broken)} broken)")
    print(f"Image types: {final_item} product shots, {final_room} room scenes")
    print(f"Saved to {CATALOG_PATH}")


if __name__ == "__main__":
    asyncio.run(validate_and_clean())
