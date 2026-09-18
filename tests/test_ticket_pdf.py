import asyncio

from integrations.snehith_client import SnehithClient
from utils.ticket_pdf import generate_ticket_pdf


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")
    await client.login()

    print("Logged in successfully!")

    booking_id = 29

    print("\nFetching confirmed ticket...")

    ticket = await client.get_ticket(
        booking_id=booking_id,
    )

    print("Booking:", ticket["booking_reference"])
    print("Status:", ticket["status"])

    print("\nGenerating PDF...")

    pdf_path = generate_ticket_pdf(
        ticket
    )

    print("\n==============================")
    print("PDF GENERATED")
    print("==============================")

    print("File:", pdf_path)


if __name__ == "__main__":
    asyncio.run(main())