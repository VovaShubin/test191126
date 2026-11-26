from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Campaign, Stream, StreamOffer
from app.weights import WeightedOffer, recalculate


def _offer_id(item: dict[str, Any]) -> int:
    return int(item.get("offer_id") or item.get("id"))


def load_stream(db: Session, stream_id: int) -> Stream | None:
    return db.scalar(
        select(Stream)
        .where(Stream.keitaro_id == stream_id)
        .options(selectinload(Stream.offers), selectinload(Stream.campaign))
    )


def sync_campaign(
    db: Session,
    remote_campaign: dict[str, Any],
    remote_streams: list[dict[str, Any]],
    offer_names: dict[int, str],
) -> Campaign:
    remote_campaign_id = int(remote_campaign["id"])
    campaign = db.scalar(
        select(Campaign)
        .where(Campaign.keitaro_id == remote_campaign_id)
        .options(selectinload(Campaign.streams).selectinload(Stream.offers))
    )
    if campaign is None:
        campaign = Campaign(keitaro_id=remote_campaign_id, name=remote_campaign.get("name", ""))
        db.add(campaign)
        db.flush()
    campaign.name = remote_campaign.get("name", campaign.name)
    campaign.synced_at = datetime.utcnow()
    streams_by_id = {stream.keitaro_id: stream for stream in campaign.streams}

    for raw_stream in remote_streams:
        remote_stream_id = int(raw_stream["id"])
        stream = streams_by_id.get(remote_stream_id)
        if stream is None:
            stream = Stream(campaign=campaign, keitaro_id=remote_stream_id)
            db.add(stream)
            db.flush()
        stream.name = raw_stream.get("name") or f"Stream {remote_stream_id}"
        stream.position = int(raw_stream.get("position") or 0)
        stream.is_dirty = False

        raw_offers = raw_stream.get("offers") or []
        local_by_offer = {item.offer_id: item for item in stream.offers}
        remote_ids: set[int] = set()
        for raw_offer in raw_offers:
            offer_id = _offer_id(raw_offer)
            remote_ids.add(offer_id)
            item = local_by_offer.get(offer_id)
            if item is None:
                item = StreamOffer(stream=stream, offer_id=offer_id)
                db.add(item)
            share = int(raw_offer.get("share") or 0)
            item.offer_name = offer_names.get(offer_id, item.offer_name or f"Offer #{offer_id}")
            item.share = share
            item.published_share = share
            item.is_removed = False
            item.published_removed = False
            item.existed_at_sync = True

        for item in stream.offers:
            if item.offer_id not in remote_ids:
                item.share = 0
                item.published_share = 0
                item.is_removed = True
                item.published_removed = True
                item.existed_at_sync = True
        stream.has_offers = bool(raw_offers or stream.offers)

    db.commit()
    db.refresh(campaign)
    return campaign


def apply_weights(stream: Stream) -> None:
    shares = recalculate(
        [
            WeightedOffer(
                offer_id=item.offer_id,
                share=item.share,
                is_removed=item.is_removed,
                is_pinned=item.is_pinned,
            )
            for item in stream.offers
        ]
    )
    for item in stream.offers:
        item.share = shares[item.offer_id]


def mark_published(stream: Stream) -> None:
    for item in stream.offers:
        item.published_share = item.share
        item.published_removed = item.is_removed
        item.existed_at_sync = True
    stream.is_dirty = False


def cancel_draft(db: Session, stream: Stream) -> None:
    for item in list(stream.offers):
        if not item.existed_at_sync:
            db.delete(item)
            stream.offers.remove(item)
        else:
            item.share = item.published_share
            item.is_removed = item.published_removed
    stream.is_dirty = False
    db.commit()

