import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so it works when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from integrations.snehith_client import SnehithClient


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")
    await client.login()
    print("Logged in successfully!")

    bus_id = 11
    journey_date = "2026-09-19"

    print(f"\nChecking seat availability for Bus {bus_id} on {journey_date}...")
    seat_data = await client.get_seats(bus_id=bus_id, journey_date=journey_date)
    available_seats = [
        s for s in seat_data.get("seats", [])
        if s.get("status") == "available"
    ]

    if len(available_seats) < 4:
        raise RuntimeError(
            f"Not enough available seats on bus {bus_id}: found {len(available_seats)}, need 4."
        )

    target_ids = [333, 334, 335, 336]
    avail_by_id = {s["id"]: s for s in available_seats}
    if all(tid in avail_by_id for tid in target_ids):
        selected_seats = [avail_by_id[tid] for tid in target_ids]
    else:
        selected_seats = available_seats[:4]

    seat_ids = [s["id"] for s in selected_seats]
    seat_numbers = [s["seat_number"] for s in selected_seats]

    print(f"Holding seats: {', '.join(seat_numbers)} (IDs: {seat_ids})")

    result = await client.hold_seats(
        bus_id=bus_id,
        journey_date=journey_date,
        seat_ids=seat_ids,
    )

    print("\n==============================")
    print("HOLD RESULT")
    print("==============================")

    print("Hold token:", result["hold_token"])
    print("Bus ID:", result["bus_id"])
    print("Journey date:", result["journey_date"])
    print("Duration:", result["duration_minutes"], "minutes")
    print("Expires at:", result["expires_at"])
    print("Message:", result["message"])

    print("\nHeld seats:")

    for seat in result["held_seats"]:
        print(
            f"{seat['seat_number']} "
            f"(ID: {seat['seat_id']}) "
            f"₹{seat['price']}"
        )


if __name__ == "__main__":
    asyncio.run(main())