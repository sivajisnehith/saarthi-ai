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

    print("Login successful!\n")

    print("Searching for buses...")

    buses = await client.search_buses(
        origin="Hyderabad",
        destination="Vijayawada",
        journey_date="2026-09-18",
        passengers=2,
        seat_type="sleeper",
        departure_time="night",
        sort_by="cheapest",
    )

    print(f"Found {len(buses)} buses.\n")

    for index, bus in enumerate(buses, start=1):
        print(
            f"{index}. "
            f"{bus['bus_name']} | "
            f"ID: {bus['bus_id']} | "
            f"₹{bus['starting_price']}"
        )

    first_bus = buses[0]

    bus_id = first_bus["bus_id"]

    print(f"\nChecking seats for bus ID {bus_id}...")

    seats = await client.get_seats(
        bus_id=bus_id,
        journey_date="2026-09-18",
    )

    print("\nSeat availability:")
    print(seats)

    print("\nGetting seat recommendations...")

    recommendations = await client.recommend_seats(
        bus_id=bus_id,
        journey_date="2026-09-18",
        window=True,
        sleeper=True,
        cheapest=True,
        limit=5,
    )

    print("\nRecommended seats:")
    print(recommendations)


if __name__ == "__main__":
    asyncio.run(main())