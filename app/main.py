from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError
from app.models import StreamOffer
from app.schemas import CampaignCreate, OfferAdd, PinUpdate
from app.service import (
    apply_weights,
    cancel_draft,
    load_stream,
    mark_published,
    sync_campaign,
)
from app.weights import WeightError

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Keitaro Wrapper")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@app.exception_handler(KeitaroError)
async def keitaro_error_handler(_: Request, exc: KeitaroError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/", response_class=HTMLResponse)
def index(request: Request, settings: Config) -> HTMLResponse:
    configured = all(
        (
            settings.keitaro_api_key,
            settings.keitaro_domain_id,
            settings.keitaro_group_id,
            settings.keitaro_traffic_source_id,
        )
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"prefix": settings.campaign_prefix, "configured": configured},
    )


def serialize_stream(stream: object) -> dict:
    return {
        "id": stream.keitaro_id,
        "name": stream.name,
        "position": stream.position,
        "has_offers": stream.has_offers,
        "dirty": stream.is_dirty,
        "offers": [
            {
                "id": item.offer_id,
                "name": item.offer_name,
                "share": item.share,
                "removed": item.is_removed,
                "pinned": item.is_pinned,
            }
            for item in stream.offers
        ],
    }


@app.get("/api/offers")
async def offers(settings: Config, q: str = "") -> list[dict]:
    result = await KeitaroClient(settings).get_offers()
    query = q.casefold().strip()
    items = [
        {"id": int(item["id"]), "name": item.get("name") or f"Offer #{item['id']}"}
        for item in result
    ]
    if query:
        items = [item for item in items if query in f"{item['id']} {item['name']}".casefold()]
    return items[:50]


@app.get("/api/campaigns")
async def campaigns(settings: Config) -> list[dict]:
    result = await KeitaroClient(settings).list_campaigns()
    return [{"id": int(item["id"]), "name": item.get("name", "")} for item in result]


@app.post("/api/campaigns", status_code=201)
async def create_campaign(payload: CampaignCreate, settings: Config, db: Db) -> dict:
    missing = [
        key
        for key, value in {
            "KEITARO_DOMAIN_ID": settings.keitaro_domain_id,
            "KEITARO_GROUP_ID": settings.keitaro_group_id,
            "KEITARO_TRAFFIC_SOURCE_ID": settings.keitaro_traffic_source_id,
        }.items()
        if value is None
    ]
    if missing:
        raise HTTPException(503, f"Не настроены: {', '.join(missing)}")

    name = (
        payload.name
        if payload.name.startswith(settings.campaign_prefix)
        else f"{settings.campaign_prefix}{payload.name}"
    )
    alias = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower()[:64]
    client = KeitaroClient(settings)
    remote_offers = await client.get_offers()
    if payload.offer_id not in {int(item["id"]) for item in remote_offers}:
        raise HTTPException(404, "Оффер не найден в Keitaro")
    campaign = await client.create_campaign(name, alias)
    campaign_id = int(campaign["id"])
    try:
        await client.create_standard_streams(campaign_id, payload.geo, payload.offer_id)
    except KeitaroError:
        try:
            await client.delete_campaign(campaign_id)
        except KeitaroError:
            pass
        raise
    remote = await client.get_campaign(campaign_id)
    streams = await client.get_streams(campaign_id)
    local = sync_campaign(
        db,
        remote,
        streams,
        {int(item["id"]): item.get("name", "") for item in remote_offers},
    )
    return {"id": local.keitaro_id, "name": local.name}


@app.post("/api/campaigns/{campaign_id}/fetch")
async def fetch_campaign(campaign_id: int, settings: Config, db: Db) -> dict:
    client = KeitaroClient(settings)
    remote = await client.get_campaign(campaign_id)
    streams = await client.get_streams(campaign_id)
    remote_offers = await client.get_offers()
    campaign = sync_campaign(
        db,
        remote,
        streams,
        {int(item["id"]): item.get("name", "") for item in remote_offers},
    )
    return {
        "id": campaign.keitaro_id,
        "name": campaign.name,
        "streams": [
            serialize_stream(stream)
            for stream in sorted(campaign.streams, key=lambda item: item.position)
        ],
    }


@app.post("/api/streams/{stream_id}/offers")
async def add_offer(stream_id: int, payload: OfferAdd, settings: Config, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    if stream is None:
        raise HTTPException(404, "Сначала загрузите кампанию")
    remote_offers = await KeitaroClient(settings).get_offers()
    names = {int(item["id"]): item.get("name", "") for item in remote_offers}
    if payload.offer_id not in names:
        raise HTTPException(404, "Оффер не найден в Keitaro")
    item = next((item for item in stream.offers if item.offer_id == payload.offer_id), None)
    if item is None:
        item = StreamOffer(
            stream=stream,
            offer_id=payload.offer_id,
            offer_name=names[payload.offer_id],
            is_removed=False,
            existed_at_sync=False,
        )
        db.add(item)
    else:
        item.is_removed = False
        item.offer_name = names[payload.offer_id]
    stream.has_offers = True
    stream.is_dirty = True
    try:
        apply_weights(stream)
        db.commit()
    except WeightError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return serialize_stream(stream)


@app.delete("/api/streams/{stream_id}/offers/{offer_id}")
def remove_offer(stream_id: int, offer_id: int, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    item = next((item for item in stream.offers if item.offer_id == offer_id), None) if stream else None
    if item is None:
        raise HTTPException(404, "Оффер не найден в потоке")
    item.is_removed = True
    item.share = 0
    stream.is_dirty = True
    try:
        apply_weights(stream)
        db.commit()
    except WeightError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return serialize_stream(stream)


@app.post("/api/streams/{stream_id}/offers/{offer_id}/restore")
def restore_offer(stream_id: int, offer_id: int, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    item = next((item for item in stream.offers if item.offer_id == offer_id), None) if stream else None
    if item is None:
        raise HTTPException(404, "Оффер не найден в архиве")
    item.is_removed = False
    stream.is_dirty = True
    try:
        apply_weights(stream)
        db.commit()
    except WeightError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return serialize_stream(stream)


@app.put("/api/streams/{stream_id}/offers/{offer_id}/pin")
def pin_offer(stream_id: int, offer_id: int, payload: PinUpdate, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    item = next((item for item in stream.offers if item.offer_id == offer_id), None) if stream else None
    if item is None or item.is_removed:
        raise HTTPException(404, "Активный оффер не найден")
    item.is_pinned = payload.pinned
    stream.is_dirty = True
    try:
        apply_weights(stream)
        db.commit()
    except WeightError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return serialize_stream(stream)


@app.post("/api/streams/{stream_id}/cancel")
def cancel(stream_id: int, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    if stream is None:
        raise HTTPException(404, "Поток не найден")
    cancel_draft(db, stream)
    return serialize_stream(stream)


@app.post("/api/streams/{stream_id}/push")
async def push(stream_id: int, settings: Config, db: Db) -> dict:
    stream = load_stream(db, stream_id)
    if stream is None:
        raise HTTPException(404, "Поток не найден")
    active = [item for item in stream.offers if not item.is_removed]
    if not active:
        raise HTTPException(409, "В потоке должен остаться хотя бы один оффер")
    if sum(item.share for item in active) != 100:
        raise HTTPException(409, "Сумма весов должна быть равна 100%")
    await KeitaroClient(settings).update_stream_offers(
        stream_id,
        [
            {"offer_id": item.offer_id, "share": item.share, "state": "active"}
            for item in active
        ],
    )
    mark_published(stream)
    db.commit()
    return serialize_stream(stream)

