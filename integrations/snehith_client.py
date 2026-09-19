import logging
import time
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

        async with httpx.AsyncClient(timeout=30.0) as client:
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

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params=params,
                headers=self._headers(),
            )
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("Snehith API GET %s | duration_ms=%.1f | status=%s", path, duration_ms, response.status_code)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                err_body = response.text
            except Exception:
                err_body = ""
            raise httpx.HTTPStatusError(
                f"{e.args[0]} - Details: {err_body}",
                request=e.request,
                response=e.response,
            ) from e

        return response.json()

    async def post(
        self,
        path: str,
        json: dict | None = None,
    ):
        await self._ensure_authenticated()

        url = f"{self.base_url}{path}"

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=json,
                headers=self._headers(),
            )
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.info("Snehith API POST %s | duration_ms=%.1f | status=%s", path, duration_ms, response.status_code)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                err_body = response.text
            except Exception:
                err_body = ""
            raise httpx.HTTPStatusError(
                f"{e.args[0]} - Details: {err_body}",
                request=e.request,
                response=e.response,
            ) from e

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
    async def hold_seats(
        self,
        bus_id: int,
        journey_date: str,
        seat_ids: list[int],
    ):
        payload = {
            "bus_id": bus_id,
            "journey_date": journey_date,
            "seat_ids": seat_ids,
        }

        return await self.post(
            "/api/seats/hold",
            json=payload,
        )
    async def create_booking(
        self,
        bus_id: int,
        journey_date: str,
        boarding_point: str,
        dropping_point: str,
        passengers: list[dict],
        hold_token: str | None = None,
    ):
        normalized_passengers = []
        gender_map = {
            "m": "M",
            "male": "M",
            "f": "F",
            "female": "F",
            "other": "Other",
            "o": "Other",
        }
        for p in passengers:
            p_copy = dict(p)
            if "gender" in p_copy and isinstance(p_copy["gender"], str):
                normalized = gender_map.get(p_copy["gender"].strip().lower())
                if normalized:
                    p_copy["gender"] = normalized
            normalized_passengers.append(p_copy)

        payload = {
            "bus_id": bus_id,
            "journey_date": journey_date,
            "boarding_point": boarding_point,
            "dropping_point": dropping_point,
            "passengers": normalized_passengers,
        }

        if hold_token:
            payload["hold_token"] = hold_token

        return await self.post(
            "/api/bookings",
            json=payload,
        )
    async def create_payment(
        self,
        booking_id: int,
        payment_method: str = "RAZORPAY_PAYMENT_LINK",
    ):
        payload = {
            "booking_id": booking_id,
            "payment_method": payment_method,
        }

        return await self.post(
            "/api/payments",
            json=payload,
        )

    async def get_bookings(self):
        return await self.get("/api/bookings")

    async def get_booking(
        self,
        booking_id: int,
    ):
        return await self.get(
            f"/api/bookings/{booking_id}",
        )
    
    async def get_payment(
        self,
        payment_id: int,
    ):
        return await self.get(
            f"/api/payments/{payment_id}",
        )

    async def get_ticket(
        self,
        booking_id: int,
    ):
        return await self.get(
            f"/api/tickets/{booking_id}",
        )
    async def deliver_payment_link(
        self,
        booking_id: int,
        channel: str,
        destination: str,
    ):
        payload = {
            "booking_id": booking_id,
            "channel": channel,
            "destination": destination,
        }

        return await self.post(
            "/api/payments/deliver-link",
            json=payload,
        )
logger = logging.getLogger('saarthi.integrations.snehith')
