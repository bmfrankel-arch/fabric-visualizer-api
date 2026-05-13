"""
Usage analytics — records page views, selections, and visualizations
made by brand-portal users, and exposes a summary endpoint for the
internal dashboard.

Auth: AuthMiddleware in main.py already gates this router. When an X-API-Key
is presented, request.state.brand is set to that brand's name; we prefer that
over any client-supplied brand value so brands can't impersonate each other.
"""

import json
import time
from typing import Any
from fastapi import APIRouter, Request
from pydantic import BaseModel
from ..database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class EventIn(BaseModel):
    event: str
    brand: str | None = None
    session_id: str | None = None
    payload: dict[str, Any] = {}


@router.post("/event")
async def log_event(event: EventIn, request: Request):
    # Trust the brand set by the auth middleware over anything the client sends.
    server_brand = getattr(request.state, "brand", None)
    resolved_brand = server_brand or event.brand or ""

    db = get_db()
    db.execute(
        "INSERT INTO analytics_events (ts, event, brand, session_id, payload, user_agent, ip) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            int(time.time()),
            event.event[:64],
            resolved_brand[:32],
            (event.session_id or "")[:64],
            json.dumps(event.payload)[:2000],
            (request.headers.get("user-agent", ""))[:200],
            (request.client.host if request.client else "")[:64],
        ),
    )
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/summary")
def summary(brand: str = "", days: int = 30):
    db = get_db()
    cutoff = int(time.time()) - days * 86400

    brand_clause = "AND brand = ?" if brand else ""
    params_brand: tuple = (brand,) if brand else ()

    totals = db.execute(
        f"SELECT brand, event, COUNT(*) as count "
        f"FROM analytics_events WHERE ts >= ? {brand_clause} "
        f"GROUP BY brand, event ORDER BY brand, count DESC",
        (cutoff,) + params_brand,
    ).fetchall()

    sessions = db.execute(
        f"SELECT brand, COUNT(DISTINCT session_id) as sessions "
        f"FROM analytics_events WHERE ts >= ? AND session_id != '' {brand_clause} "
        f"GROUP BY brand",
        (cutoff,) + params_brand,
    ).fetchall()

    daily = db.execute(
        f"SELECT date(ts, 'unixepoch') as day, brand, COUNT(*) as count "
        f"FROM analytics_events WHERE ts >= ? {brand_clause} "
        f"GROUP BY day, brand ORDER BY day DESC",
        (cutoff,) + params_brand,
    ).fetchall()

    recent = db.execute(
        f"SELECT ts, event, brand, session_id, payload "
        f"FROM analytics_events WHERE ts >= ? {brand_clause} "
        f"ORDER BY ts DESC LIMIT 100",
        (cutoff,) + params_brand,
    ).fetchall()

    db.close()
    return {
        "window_days": days,
        "totals": [dict(r) for r in totals],
        "sessions": [dict(r) for r in sessions],
        "daily": [dict(r) for r in daily],
        "recent": [dict(r) for r in recent],
    }
