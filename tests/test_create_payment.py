import asyncio

from integrations.snehith_client import SnehithClient


async def main():

    client = SnehithClient()

    print("Logging into Snehith Travels...")
    await client.login()

    print("Logged in successfully!")

    # -------------------------------------------------
    # Create payment for existing booking
    # -------------------------------------------------

    booking_id = 29

    print("\nCreating Razorpay payment...")
    print("Booking ID:", booking_id)

    payment = await client.create_payment(
        booking_id=booking_id,
    )

    print("\n==============================")
    print("PAYMENT CREATED")
    print("==============================")

    print("Payment ID:", payment.get("id"))
    print("Booking ID:", payment.get("booking_id"))
    print("Status:", payment.get("status"))
    print("Payment method:", payment.get("payment_method"))
    print("Payment URL:", payment.get("payment_url"))
    print("Provider:", payment.get("provider"))

    print("\nFull response:")
    print(payment)


if __name__ == "__main__":
    asyncio.run(main())