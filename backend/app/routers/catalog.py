"""
Catalog API — serves Dorell fabrics and furniture retailer data.

Fabric images are proxied from the Dorell Netlify site.
Furniture data comes from pre-scraped JSON catalogs.
New retailers can be added by dropping a JSON file in the app directory
and registering it in RETAILERS below.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

DATA_DIR = Path(__file__).parent.parent

# ── Dorell Fabrics ──────────────────────────────────────────────

DORELL_IMAGE_BASE = "https://dorellfabrics-patternlibrary.netlify.app/images"

_fabrics_cache = None


def _load_fabrics():
    global _fabrics_cache
    if _fabrics_cache is None:
        with open(DATA_DIR / "dorell_fabrics.json") as f:
            raw = json.load(f)
        # Enrich with full image URLs
        for p in raw:
            p["image_urls"] = [
                f"{DORELL_IMAGE_BASE}/{p['slug']}/{img}" for img in p.get("images", [])
            ]
            # Primary thumbnail
            p["thumbnail"] = p["image_urls"][0] if p["image_urls"] else ""
        _fabrics_cache = raw
    return _fabrics_cache


@router.get("/fabrics")
def list_fabrics(
    q: str = "",
    durability: str = "",
    content: str = "",
    direction: str = "",
    limit: int = Query(60, le=200),
    offset: int = 0,
):
    fabrics = _load_fabrics()
    results = fabrics

    if q:
        ql = q.lower()
        results = [
            p for p in results
            if ql in p["name"].lower()
            or any(ql in img.lower() for img in p.get("images", []))
        ]

    if durability and durability != "All":
        results = [p for p in results if durability in p.get("durability", "")]

    if content:
        cl = content.lower()
        results = [p for p in results if cl in p.get("content", "").lower()]

    if direction:
        dl = direction.lower()
        results = [p for p in results if dl in p.get("direction", "").lower()]

    total = len(results)
    page = results[offset : offset + limit]
    return {"total": total, "items": page}


@router.get("/fabrics/{slug}")
def get_fabric(slug: str):
    fabrics = _load_fabrics()
    for p in fabrics:
        if p["slug"] == slug:
            return p
    raise HTTPException(status_code=404, detail="Fabric not found")


@router.get("/fabrics-filters")
def fabrics_filters():
    """Return available filter values."""
    fabrics = _load_fabrics()
    durabilities = sorted(set(
        p.get("durability", "") for p in fabrics if p.get("durability") and p["durability"] != "TBA"
    ))
    contents = sorted(set(p.get("content", "") for p in fabrics if p.get("content") and p["content"] != "TBA"))
    directions = sorted(set(
        p.get("direction", "").strip() for p in fabrics
        if p.get("direction") and p["direction"] != "TBA"
    ))
    return {"durabilities": durabilities, "contents": contents, "directions": directions}


# ── Furniture Retailers ─────────────────────────────────────────

RETAILERS = {
    "ashley": {
        "name": "Ashley Furniture",
        "file": "ashley_catalog.json",
        "logo": "",
    },
    "arhaus": {
        "name": "Arhaus",
        "file": "arhaus_catalog.json",
        "logo": "",
    },
    "bernhardt": {
        "name": "Bernhardt",
        "file": "bernhardt_catalog.json",
        "logo": "",
    },
    "crateandbarrel": {
        "name": "Crate & Barrel",
        "file": "crateandbarrel_catalog.json",
        "logo": "",
    },
    "westelm": {
        "name": "West Elm",
        "file": "westelm_catalog.json",
        "logo": "",
    },
    "potterybarn": {
        "name": "Pottery Barn",
        "file": "potterybarn_catalog.json",
        "logo": "",
    },
    "jonathanlouis": {
        "name": "Jonathan Louis",
        "file": "jonathanlouis_catalog.json",
        "logo": "",
    },
    "livingspaces": {
        "name": "Living Spaces",
        "file": "livingspaces_catalog.json",
        "logo": "",
    },
}

_furniture_cache: dict[str, list] = {}


def _load_furniture(retailer_key: str):
    if retailer_key not in _furniture_cache:
        info = RETAILERS.get(retailer_key)
        if not info:
            return None
        filepath = DATA_DIR / info["file"]
        if not filepath.exists():
            return []
        with open(filepath) as f:
            _furniture_cache[retailer_key] = json.load(f)
    return _furniture_cache[retailer_key]


@router.get("/retailers")
def list_retailers():
    """Return list of available furniture retailers."""
    return [
        {"key": k, "name": v["name"], "logo": v["logo"]}
        for k, v in RETAILERS.items()
    ]


@router.get("/furniture/{retailer}")
def list_furniture(
    retailer: str,
    q: str = "",
    category: str = "",
    collection: str = "",
    limit: int = Query(60, le=200),
    offset: int = 0,
):
    items = _load_furniture(retailer)
    if items is None:
        raise HTTPException(status_code=404, detail=f"Retailer '{retailer}' not found")

    results = items

    if q:
        ql = q.lower()
        results = [p for p in results if ql in p.get("name", "").lower()]

    if category:
        cl = category.lower()
        results = [
            p for p in results
            if cl in p.get("type", "").lower() or cl in p.get("category", "").lower()
        ]

    if collection:
        col = collection.lower()
        results = [p for p in results if col in p.get("collection", "").lower()]

    total = len(results)
    page = results[offset : offset + limit]
    return {"total": total, "items": page}


@router.get("/furniture/{retailer}/filters")
def furniture_filters(retailer: str):
    items = _load_furniture(retailer)
    if items is None:
        raise HTTPException(status_code=404, detail=f"Retailer '{retailer}' not found")

    types = sorted(set(p.get("type", "") for p in items if p.get("type")))
    collections = sorted(set(p.get("collection", "") for p in items if p.get("collection")))
    return {"types": types, "collections": collections}
