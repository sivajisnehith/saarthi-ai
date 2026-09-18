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

    # -------------------------------------------------
    # 1. Fetch available seats
    # -------------------------------------------------

    print("\nFetching current seat availability...")
    seat_data = await client.get_seats(bus_id=bus_id, journey_date=journey_date)
    available_seats = [
        s for s in seat_data.get("seats", [])
        if s.get("status") == "available"
    ]

    if len(available_seats) < 4:
        raise RuntimeError(
            f"Not enough available seats on bus {bus_id} for {journey_date}. "
            f"Found {len(available_seats)}, need 4."
        )

    # Prefer target seats [333, 334, 335, 336] if all are available; otherwise use first 4 available seats
    target_ids = [333, 334, 335, 336]
    available_map = {s["id"]: s for s in available_seats}
    if all(tid in available_map for tid in target_ids):
        selected_seats = [available_map[tid] for tid in target_ids]
    else:
        selected_seats = available_seats[:4]

    seat_ids = [s["id"] for s in selected_seats]
    seat_numbers = [s["seat_number"] for s in selected_seats]
    print(f"Selected seats: {', '.join(seat_numbers)} (IDs: {seat_ids})")

    # -------------------------------------------------
    # 2. Hold seats
    # -------------------------------------------------

    print("\nHolding seats...")

    hold = await client.hold_seats(
        bus_id=bus_id,
        journey_date=journey_date,
        seat_ids=seat_ids,
    )

    print("Seats held successfully!")
    print("Hold token:", hold["hold_token"])
    print("Expires at:", hold.get("expires_at"))

    # -------------------------------------------------
    # 3. Create booking
    # -------------------------------------------------

    print("\nCreating booking...")

    names = ["Snehith", "Rahul", "Arjun", "Kiran"]
    ages = [20, 21, 20, 21]

    passengers = [
        {
            "seat_id": s["id"],
            "name": name,
            "age": age,
            "gender": "M",
        }
        for s, name, age in zip(selected_seats, names, ages)
    ]

    booking = await client.create_booking(
        bus_id=bus_id,
        journey_date=journey_date,
        boarding_point="Hyderabad",
        dropping_point="Vijayawada",
        passengers=passengers,
        hold_token=hold["hold_token"],
    )

    print("\n==============================")
    print("BOOKING CREATED")
    print("==============================")

    print(booking)


if __name__ == "__main__":
    asyncio.run(main())