import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..config import settings
from ..database import get_db
from ..models.schemas import FabricOut

router = APIRouter(prefix="/api/fabrics", tags=["fabrics"])


@router.get("/", response_model=list[FabricOut])
def list_fabrics(category: str = ""):
    db = get_db()
    if category:
        rows = db.execute(
            "SELECT * FROM fabrics WHERE category = ? ORDER BY created_at DESC",
            (category,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fabrics ORDER BY created_at DESC"
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@router.get("/categories")
def list_categories():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT category FROM fabrics WHERE category != '' ORDER BY category"
    ).fetchall()
    db.close()
    return [r["category"] for r in rows]


@router.get("/{fabric_id}", response_model=FabricOut)
def get_fabric(fabric_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM fabrics WHERE id = ?", (fabric_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="Fabric not found")
    return dict(row)


@router.post("/", response_model=FabricOut)
async def upload_fabric(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form(""),
    color_tags: str = Form(""),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    ext = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = settings.fabrics_dir / filename

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    with open(filepath, "wb") as f:
        f.write(content)

    fabric_name = name or (Path(file.filename).stem if file.filename else "Untitled")

    db = get_db()
    cursor = db.execute(
        "INSERT INTO fabrics (name, filename, category, color_tags) VALUES (?, ?, ?, ?)",
        (fabric_name, filename, category, color_tags),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM fabrics WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    db.close()
    return dict(row)


@router.post("/bulk")
async def upload_fabrics_bulk(
    files: list[UploadFile] = File(...),
    category: str = Form(""),
):
    results = []
    db = get_db()
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            continue
        ext = Path(file.filename).suffix if file.filename else ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = settings.fabrics_dir / filename
        content = await file.read()
        if len(content) > settings.max_upload_size:
            continue
        with open(filepath, "wb") as f:
            f.write(content)
        fabric_name = Path(file.filename).stem if file.filename else "Untitled"
        cursor = db.execute(
            "INSERT INTO fabrics (name, filename, category, color_tags) VALUES (?, ?, ?, ?)",
            (fabric_name, filename, category, ""),
        )
        results.append({"name": fabric_name, "id": cursor.lastrowid})
    db.commit()
    db.close()
    return {"uploaded": len(results), "fabrics": results}


@router.delete("/{fabric_id}")
def delete_fabric(fabric_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM fabrics WHERE id = ?", (fabric_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Fabric not found")
    filepath = settings.fabrics_dir / row["filename"]
    if filepath.exists():
        filepath.unlink()
    db.execute("DELETE FROM fabrics WHERE id = ?", (fabric_id,))
    db.commit()
    db.close()
    return {"deleted": True}
