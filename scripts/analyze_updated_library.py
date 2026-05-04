"""Analyze the Updated Photography Library against current dorell_fabrics.json.

Reports what's net-new (patterns + colorways) so we know what would be added
if we ran a sync from this source.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

LIBRARY = Path(
    r"C:\Users\BrianFrankel\OneDrive - Dorell Fabrics Co\Design"
    r"\1. Updated Photography Library"
)
JSON_PATH = Path(__file__).parent.parent / "backend" / "app" / "dorell_fabrics.json"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def folder_to_slug(name: str) -> str:
    """Normalize a folder name into a slug.

    'Anders-C0' -> 'anders-c0'
    'Awning Stripe-C0' -> 'awning-stripe-c0'
    'Adelina-UV' -> 'adelina-uv'
    """
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def file_to_target(slug: str, filename: str) -> str:
    """'Anders-C0 Birch.jpg' under slug 'anders-c0' -> 'anders-c0-birch.jpg'."""
    stem, ext = Path(filename).stem, Path(filename).suffix.lower()
    # Strip the leading folder-name token if present
    parts = stem.split(" ", 1)
    if len(parts) == 2:
        color = parts[1].strip()
    else:
        color = stem
    color_slug = re.sub(r"[\s_]+", "-", color.lower())
    color_slug = re.sub(r"-+", "-", color_slug).strip("-")
    return f"{slug}-{color_slug}{ext}"


def is_skippable_folder(name: str) -> bool:
    if re.match(r"^\d+\.", name):  # '0. Master ...', '00. Drapery ...'
        return True
    lower = name.lower()
    if "incomplete" in lower:
        return True
    return False


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    json_by_slug = {p["slug"]: set(p.get("images", [])) for p in data}

    new_patterns = []  # (slug, [target_filenames])
    updated_patterns = defaultdict(list)  # slug -> [target_filenames not in json]
    skipped = []
    folder_count = 0

    for entry in sorted(p for p in LIBRARY.iterdir() if p.is_dir()):
        name = entry.name
        if is_skippable_folder(name):
            skipped.append(name)
            continue
        folder_count += 1

        slug = folder_to_slug(name)
        # Collect image files
        images = sorted(
            f.name for f in entry.iterdir()
            if f.is_file() and f.suffix.lower() in IMG_EXTS
        )
        if not images:
            continue

        target_names = [file_to_target(slug, f) for f in images]

        if slug not in json_by_slug:
            new_patterns.append((slug, target_names, name))
        else:
            existing = json_by_slug[slug]
            new_imgs = [t for t in target_names if t not in existing]
            if new_imgs:
                updated_patterns[slug] = (new_imgs, name)

    # Reports
    print(f"Library folders scanned: {folder_count}")
    print(f"Skipped folders: {len(skipped)}")
    print(f"JSON patterns: {len(json_by_slug)}")
    print()

    print(f"=== NET-NEW PATTERNS: {len(new_patterns)} ===")
    for slug, imgs, orig in new_patterns[:30]:
        print(f"  + {slug:30s} ({len(imgs):3d} colorways)  [from '{orig}']")
    if len(new_patterns) > 30:
        print(f"  ... and {len(new_patterns) - 30} more")
    print()

    total_new_colorways = sum(len(v[0]) for v in updated_patterns.values())
    print(f"=== EXISTING PATTERNS WITH NEW COLORWAYS: {len(updated_patterns)} ({total_new_colorways} colorways) ===")
    items = list(updated_patterns.items())
    for slug, (new_imgs, orig) in items[:20]:
        sample = new_imgs[:3]
        more = "..." if len(new_imgs) > 3 else ""
        print(f"  ~ {slug:30s} +{len(new_imgs):2d}: {sample}{more}")
    if len(items) > 20:
        print(f"  ... and {len(items) - 20} more")
    print()

    if skipped:
        print(f"=== SKIPPED FOLDERS ({len(skipped)}) ===")
        for s in skipped:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
