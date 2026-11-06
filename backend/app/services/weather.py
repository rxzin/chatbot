import httpx

from core.logging import logger


class CityNotFoundError(Exception):
    """The geocoder has no match for the name. Other failures mean the service is down."""


async def fetch_open_meteo(city: str) -> dict:
    """
    Fetches the current weather and daily forecast for a given city using Open-Meteo.
    """
    normalized_city = city.strip()
    if not normalized_city:
        raise ValueError("City name is required.")

    async with httpx.AsyncClient() as client:
        try:
            geocode_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": normalized_city,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
                timeout=10.0,
            )
            geocode_resp.raise_for_status()
            geocode_data = geocode_resp.json()
        except httpx.RequestError as e:
            logger.error(f"Geocoding request failed for {normalized_city}: {e}")
            raise Exception(
                f"Failed to connect to geocoding service for {normalized_city}."
            ) from e

        results = geocode_data.get("results")
        if not results:
            raise CityNotFoundError(f"Could not find coordinates for city: {normalized_city}")

        location = results[0]
        lat = location.get("latitude")
        lon = location.get("longitude")
        resolved_city_name = location.get("name", normalized_city)
        country = location.get("country", "")

        try:
            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m,relative_humidity_2m",
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                },
                timeout=10.0,
            )
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()
        except httpx.RequestError as e:
            logger.error(f"Weather request failed for {normalized_city}: {e}")
            raise Exception(
                f"Failed to fetch weather data for {resolved_city_name}."
            ) from e

        return {
            "city": resolved_city_name,
            "country": country,
            "current": weather_data.get("current", {}),
            "current_units": weather_data.get("current_units", {}),
            "daily_forecast": weather_data.get("daily", {}),
            "daily_units": weather_data.get("daily_units", {}),
        }
