from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..database import get_db
from ..config import settings
from ..models.schemas import VisualizeRequest, VisualizationOut
from ..services.visualizer import apply_fabric_to_furniture, apply_fabric_ai, download_image

router = APIRouter(prefix="/api/visualize", tags=["visualize"])


class CatalogVisualizeRequest(BaseModel):
    """Visualize using external image URLs (from catalog data)."""
    fabric_url: str
    furniture_url: str
    fabric_name: str = ""
    furniture_name: str = ""


@router.post("/from-urls")
async def visualize_from_urls(req: CatalogVisualizeRequest):
    """Visualize using external image URLs from the catalog."""
    try:
        fabric_path = await download_image(req.fabric_url)
        furniture_path = await download_image(req.furniture_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download images: {e}")

    result_filename = apply_fabric_to_furniture(fabric_path, furniture_path)

    return {
        "result_filename": result_filename,
        "result_url": f"/uploads/results/{result_filename}",
        "fabric_name": req.fabric_name,
        "furniture_name": req.furniture_name,
    }


@router.post("/", response_model=VisualizationOut)
async def visualize(req: VisualizeRequest):
    db = get_db()
    fabric = db.execute(
        "SELECT * FROM fabrics WHERE id = ?", (req.fabric_id,)
    ).fetchone()
    furniture = db.execute(
        "SELECT * FROM furniture WHERE id = ?", (req.furniture_id,)
    ).fetchone()
    db.close()

    if not fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    if not furniture:
        raise HTTPException(status_code=404, detail="Furniture not found")

    fabric_path = settings.fabrics_dir / fabric["filename"]
    furniture_path = settings.furniture_dir / furniture["filename"]

    if not fabric_path.exists():
        raise HTTPException(status_code=404, detail="Fabric image file missing")
    if not furniture_path.exists():
        raise HTTPException(status_code=404, detail="Furniture image file missing")

    # Use AI if available, otherwise fall back to CV
    if settings.replicate_api_token:
        result_filename = await apply_fabric_ai(fabric_path, furniture_path)
    else:
        result_filename = apply_fabric_to_furniture(fabric_path, furniture_path)

    # Save to database
    db = get_db()
    cursor = db.execute(
        "INSERT INTO visualizations (fabric_id, furniture_id, result_filename) VALUES (?, ?, ?)",
        (req.fabric_id, req.furniture_id, result_filename),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM visualizations WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    db.close()

    return dict(row)


@router.get("/history", response_model=list[VisualizationOut])
def list_visualizations():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM visualizations ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.get("/{viz_id}", response_model=VisualizationOut)
def get_visualization(viz_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM visualizations WHERE id = ?", (viz_id,)
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Visualization not found")
    return dict(row)


@router.delete("/{viz_id}")
def delete_visualization(viz_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM visualizations WHERE id = ?", (viz_id,)
    ).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Visualization not found")
    result_path = settings.upload_dir / "results" / row["result_filename"]
    if result_path.exists():
        result_path.unlink()
    db.execute("DELETE FROM visualizations WHERE id = ?", (viz_id,))
    db.commit()
    db.close()
    return {"deleted": True}
