from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class KeitaroError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class KeitaroClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = f"{settings.keitaro_base_url}/admin_api/v1"

    def _headers(self) -> dict[str, str]:
        if not self.settings.keitaro_api_key:
            raise KeitaroError("KEITARO_API_KEY не задан", 503)
        return {"Api-Key": self.settings.keitaro_api_key, "Accept": "application/json"}

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method, f"{self.base_url}/{path.lstrip('/')}", headers=self._headers(), **kwargs
                )
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}") from exc
        if response.is_error:
            detail = response.text[:1000]
            raise KeitaroError(
                f"Keitaro API вернул {response.status_code}: {detail}", response.status_code
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def list_campaigns(self) -> list[dict[str, Any]]:
        return await self.request("GET", "campaigns")

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.request("GET", f"campaigns/{campaign_id}")

    async def get_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"campaigns/{campaign_id}/streams")

    async def get_offers(self) -> list[dict[str, Any]]:
        return await self.request("GET", "offers")

    async def create_campaign(self, name: str, alias: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "alias": alias,
            "type": "position",
            "state": "active",
        }
        optional_fields = {
            "domain_id": self.settings.keitaro_domain_id,
            "group_id": self.settings.keitaro_group_id,
            "traffic_source_id": self.settings.keitaro_traffic_source_id,
        }
        payload.update({key: value for key, value in optional_fields.items() if value is not None})
        return await self.request("POST", "campaigns", json=payload)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self.request("DELETE", f"campaigns/{campaign_id}")

    async def create_stream(self, campaign_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"campaign_id": campaign_id, **payload}
        try:
            return await self.request("POST", "streams", json=body)
        except KeitaroError as first_error:
            if first_error.status_code not in {404, 405}:
                raise
            return await self.request("POST", f"campaigns/{campaign_id}/streams", json=payload)

    async def create_standard_streams(
        self, campaign_id: int, geo: str, offer_id: int
    ) -> list[dict[str, Any]]:
        geo_stream = {
            "name": f"{geo} → Google",
            "type": "regular",
            "position": 1,
            "state": "active",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": "https://google.com/",
            "collect_clicks": True,
            "filter_or": False,
            "filters": [{"name": "country", "mode": "accept", "payload": [geo]}],
        }
        offer_stream = {
            "name": "Offers",
            "type": "default",
            "position": 2,
            "state": "active",
            "schema": "landings",
            "action_type": "http",
            "collect_clicks": True,
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        }
        return [
            await self.create_stream(campaign_id, geo_stream),
            await self.create_stream(campaign_id, offer_stream),
        ]

    async def update_stream_offers(
        self, stream_id: int, offers: list[dict[str, int | str]]
    ) -> dict[str, Any]:
        return await self.request("PUT", f"streams/{stream_id}", json={"offers": offers})

