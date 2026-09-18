import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so it works when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from integrations.snehith_client import SnehithClient
from tools.seat_optimizer import find_best_group


async def main():

    client = SnehithClient()

    await client.login()

    result = await client.get_seats(
        bus_id=11,
        journey_date="2026-09-18",
    )

    seats = result["seats"]

    for passengers in [2, 4, 7, 10]:

        print("\n" + "=" * 50)
        print(f"GROUP TEST: {passengers} PASSENGERS")
        print("=" * 50)

        group = find_best_group(
            seats=seats,
            passengers=passengers,
            sleeper=True,
        )

        print("Success:", group["success"])

        if group["success"]:
            print(
                "Seats:",
                group["seat_numbers"],
            )

            print(
                "Total price:",
                group["total_price"],
            )

            print(
                "Grouping:",
                group["grouping"],
            )

        else:
            print(
                "Reason:",
                group["reason"],
            )


if __name__ == "__main__":
    asyncio.run(main())