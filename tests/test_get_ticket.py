import asyncio

from integrations.snehith_client import SnehithClient


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")
    await client.login()
    print("Logged in successfully!")

    booking_id = 29

    print("\nFetching ticket...")
    print("Booking ID:", booking_id)

    ticket = await client.get_ticket(
        booking_id=booking_id,
    )

    print("\n==============================")
    print("TICKET")
    print("==============================")

    print("Booking ID:", ticket.get("booking_id"))
    print("Booking Reference:", ticket.get("booking_reference"))
    print("Status:", ticket.get("status"))

    print("\nFull response:")
    print(ticket)


if __name__ == "__main__":
    asyncio.run(main())