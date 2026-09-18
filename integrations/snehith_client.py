import httpx

from config.settings import (
    SNEHITH_API_URL,
    SNEHITH_ADMIN_EMAIL,
    SNEHITH_ADMIN_PASSWORD,
)


class SnehithClient:

    def __init__(self):
        self.base_url = SNEHITH_API_URL.rstrip("/")
        self.access_token = None

    async def login(self):
        url = f"{self.base_url}/api/auth/login"

        payload = {
            "email": SNEHITH_ADMIN_EMAIL,
            "password": SNEHITH_ADMIN_PASSWORD,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
            )

        response.raise_for_status()

        data = response.json()

        self.access_token = data["access_token"]

        return data

    async def _ensure_authenticated(self):
        if not self.access_token:
            await self.login()

    def _headers(self):
        if not self.access_token:
            raise RuntimeError("Snehith authentication required")

        return {
            "Authorization": f"Bearer {self.access_token}"
        }

    async def get(
        self,
        path: str,
        params: dict | None = None,
    ):
        await self._ensure_authenticated()

        url = f"{self.base_url}{path}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers=self._headers(),
            )

        response.raise_for_status()

        return response.json()

    async def post(
        self,
        path: str,
        json: dict | None = None,
    ):
        await self._ensure_authenticated()

        url = f"{self.base_url}{path}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=json,
                headers=self._headers(),
            )

        response.raise_for_status()

        return response.json()

    async def search_buses(
        self,
        origin: str,
        destination: str,
        journey_date: str,
        passengers: int = 1,
        bus_type: str | None = None,
        is_ac: bool | None = None,
        seat_type: str | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        departure_time: str | None = None,
        sort_by: str | None = None,
    ):
        params = {
            "from": origin,
            "to": destination,
            "journey_date": journey_date,
            "passengers": passengers,
        }

        optional_params = {
            "bus_type": bus_type,
            "is_ac": is_ac,
            "seat_type": seat_type,
            "price_min": price_min,
            "price_max": price_max,
            "departure_time": departure_time,
            "sort_by": sort_by,
        }

        for key, value in optional_params.items():
            if value is not None:
                params[key] = value
    
        return await self.get(
            "/api/buses/search",
            params=params,
        )

    async def get_seats(
        self,
        bus_id: int,
        journey_date: str,
    ):
        return await self.get(
            f"/api/buses/{bus_id}/seats",
            params={
                "journey_date": journey_date,
            },
        )

    async def recommend_seats(
        self,
        bus_id: int,
        journey_date: str,
        cheapest: bool = False,
        window: bool = False,
        aisle: bool = False,
        lower: bool = False,
        upper: bool = False,
        front: bool = False,
        rear: bool = False,
        sleeper: bool = False,
        seater: bool = False,
        maximum_budget: float | None = None,
        limit: int = 5,
    ):
        payload = {
            "journey_date": journey_date,
            "cheapest": cheapest,
            "window": window,
            "aisle": aisle,
            "lower": lower,
            "upper": upper,
            "front": front,
            "rear": rear,
            "sleeper": sleeper,
            "seater": seater,
            "limit": limit,
        }

        if maximum_budget is not None:
            payload["maximum_budget"] = maximum_budget

        return await self.post(
            f"/api/buses/{bus_id}/recommend-seats",
            json=payload,
        )
    