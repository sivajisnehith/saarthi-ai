import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from integrations.snehith_client import SnehithClient


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")

    user = await client.login()

    print("\nLogged in successfully!")
    print("User:", user["user"]["name"])
    print("Role:", user["user"]["role"])

    print("\nSearching buses...")

    buses = await client.search_buses(
        origin="Hyderabad",
        destination="Vijayawada",
        journey_date="2026-09-18",
        passengers=2,
        seat_type="sleeper",
        departure_time="night",
        sort_by="cheapest",
    )

    print("\nBus results:")
    
    for bus in buses:
        print(
            f"{bus['bus_name']} | "
            f"{bus['bus_type']} | "
            f"₹{bus['starting_price']} | "
            f"{bus['available_seats']} seats available"
        )


if __name__ == "__main__":
    asyncio.run(main())