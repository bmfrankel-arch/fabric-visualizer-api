"""Repair JSON image refs that point to files not present on disk.

For each fabric pattern, checks every image filename in the JSON against
the catalog dir. If the file doesn't exist:
  1. Search case-insensitively for the exact name
  2. Search normalized (lowercase, hyphens) for a match
  3. If still no match, drop the ref

Reports actions and writes the cleaned JSON.
"""

import json
import re
import sys
from pathlib import Path

CATALOG_IMAGES = Path(
    r"C:\Users\BrianFrankel\OneDrive - Dorell Fabrics Co\Design"
    r"\2. New Folders Made - Brian\00. dorell-full-catalog\images"
)
JSON_PATH = Path(__file__).parent.parent / "backend" / "app" / "dorell_fabrics.json"


def normalize(name: str) -> str:
    """Normalize a filename for fuzzy comparison: lowercase, hyphens, single ext."""
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    s = re.sub(r"\s+", "-", stem.strip().lower())
    s = re.sub(r"[_\s]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return f"{s}{ext}"


def main(apply: bool):
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    renames: list[tuple[str, str, str]] = []  # (slug, old, new)
    drops: list[tuple[str, str]] = []  # (slug, ref)

    for fabric in data:
        slug = fabric["slug"]
        slug_dir = CATALOG_IMAGES / slug
        if not slug_dir.exists():
            for img in fabric.get("images", []):
                drops.append((slug, img))
            fabric["images"] = []
            continue

        # Build lookup tables for what's actually on disk
        on_disk = {p.name for p in slug_dir.iterdir() if p.is_file()}
        case_insensitive = {n.lower(): n for n in on_disk}
        normalized = {normalize(n): n for n in on_disk}

        new_imgs = []
        for ref in fabric.get("images", []):
            if ref in on_disk:
                new_imgs.append(ref)
                continue
            # Try case-insensitive
            if ref.lower() in case_insensitive:
                actual = case_insensitive[ref.lower()]
                renames.append((slug, ref, actual))
                new_imgs.append(actual)
                continue
            # Try fuzzy normalized
            n = normalize(ref)
            if n in normalized:
                actual = normalized[n]
                renames.append((slug, ref, actual))
                new_imgs.append(actual)
                continue
            drops.append((slug, ref))
        fabric["images"] = new_imgs

    print(f"Renames (filename casing/format adjusted): {len(renames)}")
    print(f"Drops   (no matching file found):          {len(drops)}")
    print()

    if renames:
        print("Sample renames:")
        for slug, old, new in renames[:15]:
            print(f"  {slug}: {old}  ->  {new}")
        if len(renames) > 15:
            print(f"  ... and {len(renames) - 15} more")
        print()

    if drops:
        print("Sample drops:")
        for slug, ref in drops[:15]:
            print(f"  {slug}: {ref}")
        if len(drops) > 15:
            print(f"  ... and {len(drops) - 15} more")
        print()

    # Drop any patterns that ended up with zero images
    empty_patterns = [p["slug"] for p in data if not p.get("images")]
    if empty_patterns:
        print(f"Patterns with zero remaining images: {len(empty_patterns)}")
        for s in empty_patterns[:10]:
            print(f"  - {s}")
        if len(empty_patterns) > 10:
            print(f"  ... and {len(empty_patterns) - 10} more")

    if not apply:
        print("\n--- DRY RUN --- pass --apply to write")
        return

    # Filter out empty patterns
    data = [p for p in data if p.get("images")]
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nWrote {len(data)} patterns to {JSON_PATH}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
