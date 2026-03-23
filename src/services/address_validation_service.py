import httpx

from src.services.settings import Settings


class AddressValidationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def suggest_address(self, address_text: str | None) -> dict | None:
        if not address_text:
            return None
        if not self.settings.google_maps_api_key:
            return None

        params = {
            "address": address_text,
            "key": self.settings.google_maps_api_key,
            "region": self.settings.google_maps_region,
            "language": self.settings.google_maps_language,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("results") or []
        if payload.get("status") != "OK" or not results:
            return None

        first = results[0]
        formatted_address = first.get("formatted_address")
        geometry = first.get("geometry", {}).get("location", {})
        latitude = geometry.get("lat")
        longitude = geometry.get("lng")

        if not formatted_address:
            return None

        suggestion = {
            "formatted_address": formatted_address,
            "latitude": latitude,
            "longitude": longitude,
            "map_url": self._build_map_url(latitude, longitude),
        }
        if self._normalize_address(formatted_address) == self._normalize_address(address_text):
            return None
        return suggestion

    @staticmethod
    def _normalize_address(value: str) -> str:
        return " ".join(value.lower().replace(",", " ").split())

    @staticmethod
    def _build_map_url(latitude: float | None, longitude: float | None) -> str | None:
        if latitude is None or longitude is None:
            return None
        return f"https://maps.google.com/?q={latitude},{longitude}"
