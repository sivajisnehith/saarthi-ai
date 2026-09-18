from strands import tool

from integrations.snehith_client import SnehithClient


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