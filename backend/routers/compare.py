from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from backend.services.compare_service import APP_META, get_compare_data

router = APIRouter()


@router.get("")
async def compare_data(
    app_keys: Optional[list[str]] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    platform: Optional[str] = Query(default=None, pattern="^(google_play|app_store)$"),
) -> dict:
    return get_compare_data(
        app_keys=app_keys,
        date_from=date_from,
        date_to=date_to,
        platform=platform,
    )


@router.get("/apps")
async def compare_apps() -> list[dict]:
    return [
        {k: app[k] for k in ("key", "name", "isSelf", "color")}
        for app in APP_META
    ]
