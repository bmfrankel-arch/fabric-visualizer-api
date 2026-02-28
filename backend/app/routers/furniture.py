import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import settings
from ..database import get_db
from ..models.schemas import FurnitureOut

router = APIRouter(prefix="/api/furniture", tags=["furniture"])


@router.get("/", response_model=list[FurnitureOut])
def list_furniture(category: str = ""):
    db = get_db()
    if category:
        rows = db.execute(
            "SELECT * FROM furniture WHERE category = ? ORDER BY created_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM furniture ORDER BY created_at DESC"
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.get("/categories")
def list_categories():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT category FROM furniture WHERE category != '' ORDER BY category"
    ).fetchall()
    db.close()
    return [r["category"] for r in rows]


@router.get("/{furniture_id}", response_model=FurnitureOut)
def get_furniture(furniture_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM furniture WHERE id = ?", (furniture_id,)
    ).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Furniture not found")
    return dict(row)


@router.post("/", response_model=FurnitureOut)
async def upload_furniture(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form(""),
    source_url: str = Form(""),
    source_site: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    ext = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = settings.furniture_dir / filename

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    with open(filepath, "wb") as f:
        f.write(content)

    furniture_name = name or (
        Path(file.filename).stem if file.filename else "Untitled"
    )

    db = get_db()
    cursor = db.execute(
        "INSERT INTO furniture (name, filename, source_url, source_site, category) VALUES (?, ?, ?, ?, ?)",
        (furniture_name, filename, source_url, source_site, category),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM furniture WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    db.close()
    return dict(row)


@router.delete("/{furniture_id}")
def delete_furniture(furniture_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM furniture WHERE id = ?", (furniture_id,)
    ).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Furniture not found")
    filepath = settings.furniture_dir / row["filename"]
    if filepath.exists():
        filepath.unlink()
    db.execute("DELETE FROM furniture WHERE id = ?", (furniture_id,))
    db.commit()
    db.close()
    return {"deleted": True}
