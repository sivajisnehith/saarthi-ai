import logging
from pathlib import Path
from strands import tool

from integrations.snehith_client import SnehithClient
from integrations.email_client import EmailClient
from integrations.whatsapp_client import WhatsAppClient
from tools.seat_optimizer import find_best_group
from tools.seat_optimizer import find_best_group
from utils.ticket_pdf import generate_ticket_pdf
from voice.progress import notify_tool_execution_start

logger = logging.getLogger('saarthi.tools.bus_tools')
client = SnehithClient()
email_client = EmailClient()
whatsapp_client = WhatsAppClient()


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
    await notify_tool_execution_start("search_buses")

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
    await notify_tool_execution_start("get_seats")

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
    await notify_tool_execution_start("create_booking")

    # Strict validation of required fields to avoid malformed inputs / 422 errors
    missing = []
    if not bus_id or not isinstance(bus_id, int) or bus_id <= 0:
        missing.append("valid integer bus_id")
    if not journey_date or not isinstance(journey_date, str):
        missing.append("journey_date (YYYY-MM-DD)")
    if not hold_token or not isinstance(hold_token, str) or not hold_token.strip():
        missing.append("hold_token")
    if not boarding_point or not isinstance(boarding_point, str) or not boarding_point.strip():
        missing.append("boarding_point")
    if not dropping_point or not isinstance(dropping_point, str) or not dropping_point.strip():
        missing.append("dropping_point")
    if not passengers or not isinstance(passengers, list) or len(passengers) == 0:
        missing.append("passengers (non-empty list of passenger dictionaries)")
    else:
        for idx, p in enumerate(passengers):
            if not isinstance(p, dict):
                missing.append(f"passengers[{idx}] must be a dictionary")
                continue
            if not p.get("name") or not str(p.get("name")).strip():
                missing.append(f"passengers[{idx}].name")
            if p.get("age") is None:
                missing.append(f"passengers[{idx}].age")
            if not p.get("gender"):
                missing.append(f"passengers[{idx}].gender")
            if not p.get("seat_number") and not p.get("seat_id"):
                missing.append(f"passengers[{idx}].seat_number")

    if missing:
        err_msg = (
            f"Validation failed for create_booking arguments: {', '.join(missing)}. "
            "All fields (bus_id, journey_date, hold_token, boarding_point, dropping_point, passengers) are required."
        )
        logger.warning("create_booking rejected: %s", err_msg)
        return {
            "success": False,
            "error": "VALIDATION_ERROR",
            "missing_fields": missing,
            "reason": err_msg,
        }

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
    await notify_tool_execution_start("create_payment")

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
    await notify_tool_execution_start("get_payment_status")

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
    await notify_tool_execution_start("generate_ticket")

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
async def deliver_ticket_to_whatsapp(
    booking_id: int,
    destination: str,
    ticket_path: str | None = None,
) -> dict:
    """Send a generated ticket PDF to the customer's WhatsApp number.

    Use only after the customer explicitly confirms they want the ticket sent
    to the WhatsApp number previously provided for this booking.
    """
    await notify_tool_execution_start("deliver_ticket_to_whatsapp")
    customer_name = "Customer"
    booking_reference = f"ST-{booking_id}"

    # Auto-generate or verify ticket PDF if not provided or missing
    if not ticket_path or not Path(ticket_path).is_file():
        logger.info(
            "Ticket PDF path '%s' not found or not provided. Generating PDF for booking_id=%s...",
            ticket_path,
            booking_id,
        )
        ticket = await client.get_ticket(booking_id=booking_id)
        if ticket.get("status") != "CONFIRMED":
            return {
                "success": False,
                "booking_id": booking_id,
                "reason": (
                    "The ticket cannot be delivered because the booking status is "
                    f"{ticket.get('status')}."
                ),
            }
        ticket_path = generate_ticket_pdf(ticket)
        booking_reference = ticket.get("booking_reference", booking_reference)
        passengers = ticket.get("passengers", [])
        if passengers and passengers[0].get("name"):
            customer_name = passengers[0]["name"]
    else:
        try:
            ticket = await client.get_ticket(booking_id=booking_id)
            booking_reference = ticket.get("booking_reference", booking_reference)
            passengers = ticket.get("passengers", [])
            if passengers and passengers[0].get("name"):
                customer_name = passengers[0]["name"]
        except Exception:
            pass

    try:
        result = await whatsapp_client.send_ticket(
            destination=destination,
            ticket_path=ticket_path,
            customer_name=customer_name,
            booking_reference=booking_reference,
        )
        return {
            **result,
            "booking_id": booking_id,
            "ticket_path": ticket_path,
            "status": "SENT",
            "message": "I've sent the ticket to your WhatsApp.",
        }
    except Exception as e:
        logger.error(
            "WhatsApp ticket delivery failed for booking_id=%s | destination=%s: %s",
            booking_id,
            destination,
            e,
        )
        return {
            "success": False,
            "booking_id": booking_id,
            "destination": destination,
            "status": "FAILED",
            "reason": str(e),
            "message": "I couldn't send the ticket to WhatsApp. I can try again.",
        }


@tool
async def deliver_ticket_to_email(
    booking_id: int,
    destination: str,
    ticket_path: str | None = None,
) -> dict:
    """Email a generated ticket PDF to the customer.

    Use only after the customer provides and explicitly confirms the email
    address to use for this booking.
    """
    await notify_tool_execution_start("deliver_ticket_to_email")
    if not ticket_path or not Path(ticket_path).is_file():
        logger.info(
            "Ticket PDF path '%s' not found or not provided. Generating PDF for booking_id=%s...",
            ticket_path,
            booking_id,
        )
        ticket = await client.get_ticket(booking_id=booking_id)
        if ticket.get("status") != "CONFIRMED":
            return {
                "success": False,
                "booking_id": booking_id,
                "destination": destination,
                "status": "FAILED",
                "reason": (
                    "The ticket cannot be delivered because the booking status is "
                    f"{ticket.get('status')}."
                ),
                "message": "I couldn't email your ticket because the booking is not confirmed.",
            }
        ticket_path = generate_ticket_pdf(ticket)

    try:
        result = await email_client.send_ticket(
            destination=destination,
            ticket_path=ticket_path,
        )
        return {
            **result,
            "booking_id": booking_id,
            "ticket_path": ticket_path,
            "status": "SENT",
            "message": "Done. I've emailed your ticket.",
        }
    except Exception as e:
        logger.error(
            "Email ticket delivery failed for booking_id=%s | destination=%s: %s",
            booking_id,
            destination,
            e,
        )
        return {
            "success": False,
            "booking_id": booking_id,
            "destination": destination,
            "status": "FAILED",
            "reason": str(e),
            "message": "I couldn't email your ticket. I can try again.",
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
    await notify_tool_execution_start("deliver_payment_link")
    result = await client.deliver_payment_link(
        booking_id=booking_id,
        channel="WHATSAPP",
        destination=destination,
    )

    return result
