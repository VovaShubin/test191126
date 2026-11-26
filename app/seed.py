import asyncio
import re

from app.config import get_settings
from app.db import SessionLocal
from app.keitaro import KeitaroClient, KeitaroError
from app.service import sync_campaign


async def seed() -> int:
    settings = get_settings()
    required = {
        "KEITARO_API_KEY": settings.keitaro_api_key,
        "KEITARO_DOMAIN_ID": settings.keitaro_domain_id,
        "KEITARO_GROUP_ID": settings.keitaro_group_id,
        "KEITARO_TRAFFIC_SOURCE_ID": settings.keitaro_traffic_source_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Не заполнены настройки: {', '.join(missing)}")

    full_name = (
        settings.seed_campaign_name
        if settings.seed_campaign_name.startswith(settings.campaign_prefix)
        else f"{settings.campaign_prefix}{settings.seed_campaign_name}"
    )
    client = KeitaroClient(settings)
    campaigns = await client.list_campaigns()
    campaign = next((item for item in campaigns if item.get("name") == full_name), None)
    created = campaign is None

    offers = await client.get_offers()
    offer_names = {int(item["id"]): item.get("name", "") for item in offers}
    if settings.seed_offer_id not in offer_names:
        raise RuntimeError(f"Оффер #{settings.seed_offer_id} не найден в Keitaro")

    if campaign is None:
        alias = re.sub(r"[^a-zA-Z0-9_-]+", "-", full_name).strip("-").lower()[:64]
        campaign = await client.create_campaign(full_name, alias)
        campaign_id = int(campaign["id"])
        try:
            await client.create_standard_streams(
                campaign_id, settings.seed_geo, settings.seed_offer_id
            )
        except KeitaroError:
            try:
                await client.delete_campaign(campaign_id)
            except KeitaroError:
                pass
            raise

    campaign_id = int(campaign["id"])
    remote_campaign = await client.get_campaign(campaign_id)
    remote_streams = await client.get_streams(campaign_id)
    with SessionLocal() as db:
        sync_campaign(db, remote_campaign, remote_streams, offer_names)

    action = "Создана" if created else "Уже существует"
    print(
        f"{action} кампания #{campaign_id}: {full_name} "
        f"(GEO {settings.seed_geo}, offer #{settings.seed_offer_id})"
    )
    return campaign_id


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()

