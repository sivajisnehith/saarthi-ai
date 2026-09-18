from strands import tool

from integrations.snehith_client import SnehithClient
from tools.seat_optimizer import find_best_group
from tools.seat_optimizer import find_best_group
from utils.ticket_pdf import generate_ticket_pdf

client = SnehithClient()


@tool
async def search_buses(
    origin: str,
    destination: str,
    journey_date: str,
    passengers: int = 1,
    seat_type: str | None = None,
    is_ac: bool | None = None,
    departure_time: str | None = None,
    sort_by: str | None = None,
) -> dict:
    """
    Search available buses on Snehith Travels.

    Use this tool when a customer wants to find buses
    between two locations for a specific journey date.

    Args:
        origin: Starting city.
        destination: Destination city.
        journey_date: Journey date in YYYY-MM-DD format.
        passengers: Number of passengers.
        seat_type: Optional seat type such as sleeper or seater.
        is_ac: Optional AC filter.
        departure_time: Optional time period such as morning,
            afternoon, evening, or night.
        sort_by: Optional sorting such as cheapest,
            earliest_departure, or shortest_journey.

    Returns:
        Available bus options from Snehith Travels.
    """

    buses = await client.search_buses(
        origin=origin,
        destination=destination,
        journey_date=journey_date,
        passengers=passengers,
        seat_type=seat_type,
        is_ac=is_ac,
        departure_time=departure_time,
        sort_by=sort_by,
    )

    return {
        "origin": origin,
        "destination": destination,
        "journey_date": journey_date,
        "passengers": passengers,
        "buses": buses,
    }

@tool
async def get_seats(
    bus_id: int,
    journey_date: str,
) -> dict:
    """
    Get the current seat availability for a specific bus and journey date.

    Args:
        bus_id: ID of the bus.
        journey_date: Journey date in YYYY-MM-DD format.

    Returns:
        Current seat availability.
    """

    result = await client.get_seats(
        bus_id=bus_id,
        journey_date=journey_date,
    )

    return result

@tool
async def recommend_seats(
    bus_id: int,
    journey_date: str,
    passengers: int = 1,
    cheapest: bool = False,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
    maximum_budget: float | None = None,
) -> dict:
    """
    Recommend available seats based on customer preferences.

    Args:
        bus_id: ID of the bus.
        journey_date: Journey date in YYYY-MM-DD format.
        passengers: Number of seats needed.
        cheapest: Prefer cheaper seats.
        window: Prefer window seats.
        aisle: Prefer aisle seats.
        lower: Prefer lower-deck seats.
        upper: Prefer upper-deck seats.
        front: Prefer front seats.
        rear: Prefer rear seats.
        sleeper: Prefer sleeper seats.
        seater: Prefer seater seats.
        maximum_budget: Maximum acceptable price per seat.

    Returns:
        Ranked seat recommendations.
    """

    result = await client.recommend_seats(
        bus_id=bus_id,
        journey_date=journey_date,
        cheapest=cheapest,
        window=window,
        aisle=aisle,
        lower=lower,
        upper=upper,
        front=front,
        rear=rear,
        sleeper=sleeper,
        seater=seater,
        maximum_budget=maximum_budget,
        limit=max(passengers, 5),
    )

    return result
@tool
async def find_group_seats(
    bus_id: int,
    journey_date: str,
    passengers: int,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
) -> dict:
    """
    Find the most compact group of available seats for multiple passengers.

    Prioritizes keeping passengers together while respecting
    requested seat preferences.

    Args:
        bus_id: Snehith Travels bus ID.
        journey_date: Journey date in YYYY-MM-DD format.
        passengers: Number of passengers.
        window: Prefer window seats.
        aisle: Prefer aisle seats.
        lower: Prefer lower-deck seats.
        upper: Prefer upper-deck seats.
        front: Prefer front seats.
        rear: Prefer rear seats.
        sleeper: Prefer sleeper seats.
        seater: Prefer seater seats.

    Returns:
        Best available group of seats.
    """

    seat_data = await client.get_seats(
        bus_id=bus_id,
        journey_date=journey_date,
    )

    seats = seat_data.get("seats", [])

    result = find_best_group(
        seats=seats,
        passengers=passengers,
        window=window,
        aisle=aisle,
        lower=lower,
        upper=upper,
        front=front,
        rear=rear,
        sleeper=sleeper,
        seater=seater,
    )

    return result

@tool
async def find_group_seats(
    bus_id: int,
    journey_date: str,
    passengers: int,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
) -> dict:
    """
    Find the best available group of seats for multiple passengers.

    Prioritizes keeping passengers together while respecting
    requested seat preferences.
    """

    if passengers < 1 or passengers > 10:
        return {
            "success": False,
            "reason": "The supported group size is between 1 and 10 passengers.",
        }

    # Get the actual current seat availability from Snehith.
    seat_data = await client.get_seats(
        bus_id=bus_id,
        journey_date=journey_date,
    )

    seats = seat_data.get("seats", [])

    # Run deterministic seat optimization.
    result = find_best_group(
        seats=seats,
        passengers=passengers,
        window=window,
        aisle=aisle,
        lower=lower,
        upper=upper,
        front=front,
        rear=rear,
        sleeper=sleeper,
        seater=seater,
    )

    return result
@tool
async def hold_seats(
    bus_id: int,
    journey_date: str,
    seat_ids: list[int],
) -> dict:
    """
    Temporarily hold selected seats for a booking.

    The hold is created by Snehith Travels and returns a hold token
    and expiry information.
    """

    result = await client.hold_seats(
        bus_id=bus_id,
        journey_date=journey_date,
        seat_ids=seat_ids,
    )

    return result
@tool
async def create_booking(
    bus_id: int,
    journey_date: str,
    boarding_point: str,
    dropping_point: str,
    passengers: list[dict],
    hold_token: str,
) -> dict:
    """
    Create a booking using seats that have already been held.

    The customer must explicitly confirm the booking before this
    tool is called.
    """

    result = await client.create_booking(
        bus_id=bus_id,
        journey_date=journey_date,
        boarding_point=boarding_point,
        dropping_point=dropping_point,
        passengers=passengers,
        hold_token=hold_token,
    )

    return result


@tool
async def create_payment(
    booking_id: int,
) -> dict:
    """
    Create a Razorpay payment link for a confirmed booking.

    Only call this after the customer explicitly confirms that
    they want to proceed with payment.
    """

    result = await client.create_payment(
        booking_id=booking_id,
    )

    return result


@tool
async def get_payment_status(
    payment_id: int,
) -> dict:
    """
    Check the authoritative payment status of a payment.
    """

    result = await client.get_payment(
        payment_id=payment_id,
    )

    return result


@tool
async def get_ticket(
    booking_id: int,
) -> dict:
    """
    Retrieve the confirmed digital ticket for a booking.
    """

    result = await client.get_ticket(
        booking_id=booking_id,
    )

    return result

@tool
async def generate_ticket(
    booking_id: int,
) -> dict:
    """
    Retrieve a confirmed ticket and generate its PDF.

    The booking must already be confirmed.
    """

    ticket = await client.get_ticket(
        booking_id=booking_id,
    )

    if ticket.get("status") != "CONFIRMED":
        return {
            "success": False,
            "reason": (
                "The ticket cannot be generated because "
                f"the booking status is {ticket.get('status')}."
            ),
        }

    pdf_path = generate_ticket_pdf(
        ticket
    )

    return {
        "success": True,
        "booking_id": booking_id,
        "booking_reference": ticket["booking_reference"],
        "pdf_path": pdf_path,
        "ticket": ticket,
    }
@tool
async def deliver_payment_link(
    booking_id: int,
    destination: str,
) -> dict:
    """
    Send the customer's Razorpay payment link to their WhatsApp number.
    The customer must provide and confirm the WhatsApp number before this tool is used.
    """
    result = await client.deliver_payment_link(
        booking_id=booking_id,
        channel="WHATSAPP",
        destination=destination,
    )

    return result