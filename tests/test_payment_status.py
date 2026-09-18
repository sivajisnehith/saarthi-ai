import asyncio

from integrations.snehith_client import SnehithClient


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")
    await client.login()
    print("Logged in successfully!")

    payment_id = 23

    print("\nChecking payment status...")
    print("Payment ID:", payment_id)

    payment = await client.get_payment(
        payment_id=payment_id,
    )

    print("\n==============================")
    print("PAYMENT STATUS")
    print("==============================")

    print("Payment ID:", payment.get("id"))
    print("Booking ID:", payment.get("booking_id"))
    print("Amount:", payment.get("amount"))
    print("Status:", payment.get("status"))

    print("\nFull response:")
    print(payment)


if __name__ == "__main__":
    asyncio.run(main())