from fastapi import APIRouter, HTTPException
from ..database import get_db
from ..models.schemas import ScraperConfig, ScraperConfigOut
from ..services.scraper import FurnitureScraper

router = APIRouter(prefix="/api/scraper", tags=["scraper"])


@router.get("/configs", response_model=list[ScraperConfigOut])
def list_configs():
    db = get_db()
    rows = db.execute("SELECT * FROM scraper_configs ORDER BY site_name").fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.post("/configs", response_model=ScraperConfigOut)
def add_config(config: ScraperConfig):
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO scraper_configs (site_name, base_url, product_selector, image_selector, name_selector, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                config.site_name,
                config.base_url,
                config.product_selector,
                config.image_selector,
                config.name_selector,
                1 if config.enabled else 0,
            ),
        )
        db.commit()
        row = db.execute(
            "SELECT * FROM scraper_configs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        db.close()
        return dict(row)
    except Exception as e:
        db.close()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/configs/{config_id}")
def delete_config(config_id: int):
    db = get_db()
    db.execute("DELETE FROM scraper_configs WHERE id = ?", (config_id,))
    db.commit()
    db.close()
    return {"deleted": True}


@router.post("/run/{config_id}")
async def run_scraper(config_id: int, url: str = "", max_items: int = 10):
    db = get_db()
    row = db.execute(
        "SELECT * FROM scraper_configs WHERE id = ?", (config_id,)
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Scraper config not found")

    config = dict(row)
    scraper = FurnitureScraper(config)
    target_url = url or config["base_url"]

    try:
        results = await scraper.scrape_and_save(target_url, max_items)
        return {"scraped": len(results), "items": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")


@router.post("/scrape-url")
async def scrape_single_url(url: str, site_name: str = "manual"):
    """Scrape a single product URL without needing a saved config."""
    config = {
        "site_name": site_name,
        "base_url": url,
        "image_selector": "img",
        "name_selector": "h1",
    }
    scraper = FurnitureScraper(config)
    try:
        result = await scraper.scrape_single_url(url)
        if result:
            return result
        raise HTTPException(
            status_code=404, detail="Could not extract furniture image from URL"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")
