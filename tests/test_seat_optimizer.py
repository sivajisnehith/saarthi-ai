import asyncio
import sys
from pathlib import Path

# Add project root to sys.path so script can be run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from integrations.snehith_client import SnehithClient
from tools.seat_optimizer import find_best_group


async def main():

    client = SnehithClient()

    await client.login()

    print("Getting seats from Snehith...\n")

    result = await client.get_seats(
        bus_id=11,
        journey_date="2026-09-18",
    )

    seats = result["seats"]

    print(
        f"Available seats: {result['available_seats']}"
    )

    # -------------------------------------------------
    # Test 2 passengers
    # -------------------------------------------------

    print("\n==============================")
    print("TEST: 2 PASSENGERS")
    print("==============================")

    group = find_best_group(
        seats,
        passengers=2,
        sleeper=True,
        window=True,
    )

    print(group)

    # -------------------------------------------------
    # Test 4 passengers
    # -------------------------------------------------

    print("\n==============================")
    print("TEST: 4 PASSENGERS")
    print("==============================")

    group = find_best_group(
        seats,
        passengers=4,
        sleeper=True,
        window=True,
    )

    print(group)

    # -------------------------------------------------
    # Test 7 passengers
    # -------------------------------------------------

    print("\n==============================")
    print("TEST: 7 PASSENGERS")
    print("==============================")

    group = find_best_group(
        seats,
        passengers=7,
        sleeper=True,
    )

    print(group)


if __name__ == "__main__":
    asyncio.run(main())