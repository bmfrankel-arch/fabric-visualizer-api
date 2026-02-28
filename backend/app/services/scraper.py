import uuid
import httpx
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ..config import settings
from ..database import get_db


class FurnitureScraper:
    """Configurable scraper for furniture product pages."""

    def __init__(self, config: dict):
        self.site_name = config["site_name"]
        self.base_url = config["base_url"]
        self.product_selector = config.get("product_selector", "")
        self.image_selector = config.get("image_selector", "img")
        self.name_selector = config.get("name_selector", "h1")

    async def scrape_listing(self, url: str, max_items: int = 20) -> list[dict]:
        """Scrape a listing/category page for product links."""
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FabricVisualizer/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        products = []

        if self.product_selector:
            elements = soup.select(self.product_selector)[:max_items]
            for el in elements:
                link = el.get("href") or el.find("a", href=True)
                if link:
                    href = link["href"] if isinstance(link, dict) else (
                        link.get("href") if hasattr(link, "get") else str(link)
                    )
                    products.append(urljoin(url, href))

        return products

    async def scrape_product(self, url: str) -> dict | None:
        """Scrape a single product page for image and name."""
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FabricVisualizer/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract product name
            name_el = soup.select_one(self.name_selector)
            name = name_el.get_text(strip=True) if name_el else "Unknown"

            # Extract product image
            img_el = soup.select_one(self.image_selector)
            if not img_el:
                return None

            img_url = img_el.get("src") or img_el.get("data-src") or ""
            if not img_url:
                return None
            img_url = urljoin(url, img_url)

            # Download image
            img_resp = await client.get(img_url)
            img_resp.raise_for_status()

            content_type = img_resp.headers.get("content-type", "")
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"

            filename = f"{uuid.uuid4().hex}{ext}"
            filepath = settings.furniture_dir / filename

            with open(filepath, "wb") as f:
                f.write(img_resp.content)

            return {
                "name": name,
                "filename": filename,
                "source_url": url,
                "source_site": self.site_name,
            }

    async def scrape_and_save(self, url: str, max_items: int = 20) -> list[dict]:
        """Scrape products and save to database."""
        product_urls = await self.scrape_listing(url, max_items)
        results = []

        for product_url in product_urls:
            try:
                product = await self.scrape_product(product_url)
                if product:
                    db = get_db()
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO furniture (name, filename, source_url, source_site, category) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            product["name"],
                            product["filename"],
                            product["source_url"],
                            product["source_site"],
                            "",
                        ),
                    )
                    db.commit()
                    product["id"] = cursor.lastrowid
                    db.close()
                    results.append(product)
            except Exception as e:
                print(f"Error scraping {product_url}: {e}")
                continue

        return results

    async def scrape_single_url(self, url: str) -> dict | None:
        """Scrape a single product URL directly and save to database."""
        product = await self.scrape_product(url)
        if product:
            db = get_db()
            cursor = db.execute(
                "INSERT OR IGNORE INTO furniture (name, filename, source_url, source_site, category) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    product["name"],
                    product["filename"],
                    product["source_url"],
                    product["source_site"],
                    "",
                ),
            )
            db.commit()
            product["id"] = cursor.lastrowid
            db.close()
        return product
