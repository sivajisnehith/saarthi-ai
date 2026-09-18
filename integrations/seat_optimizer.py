from collections import defaultdict


def seat_distance(a: dict, b: dict) -> float:
    """
    Approximate physical distance between two seats.

    Same row is preferred.
    Nearby rows are preferred over distant rows.
    """

    row_distance = abs(a["row"] - b["row"])
    column_distance = abs(a["column"] - b["column"])

    return row_distance * 3 + column_distance


def preference_score(
    seat: dict,
    *,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
) -> float:

    score = 0

    if window and seat["window"]:
        score += 20

    if aisle and seat["aisle"]:
        score += 20

    if lower and seat["upper_lower"] == "lower":
        score += 15

    if upper and seat["upper_lower"] == "upper":
        score += 15

    if front and seat["front_rear"] == "front":
        score += 10

    if rear and seat["front_rear"] == "rear":
        score += 10

    if sleeper and seat["seat_type"] == "sleeper":
        score += 20

    if seater and seat["seat_type"] == "seater":
        score += 20

    return score


def build_adjacency_graph(seats: list[dict]) -> dict[int, set[int]]:
    """
    Build a graph where each seat is connected to physically
    nearby seats.

    Seats on the same deck and same/nearby rows are considered
    adjacent candidates.
    """

    graph = defaultdict(set)

    for i, seat_a in enumerate(seats):

        for j, seat_b in enumerate(seats):

            if i == j:
                continue

            # Different decks should not be considered directly adjacent.
            if seat_a["upper_lower"] != seat_b["upper_lower"]:
                continue

            row_difference = abs(
                seat_a["row"] - seat_b["row"]
            )

            column_difference = abs(
                seat_a["column"] - seat_b["column"]
            )

            # Same row and nearby physical columns.
            same_row = (
                row_difference == 0
                and column_difference <= 3
            )

            # Seats immediately behind/in front of each other.
            nearby_row = (
                row_difference == 1
                and column_difference <= 1
            )

            if same_row or nearby_row:
                graph[seat_a["id"]].add(seat_b["id"])

    return graph


def group_togetherness_score(
    seats: list[dict],
) -> float:

    if not seats:
        return float("-inf")

    # -------------------------------------------------
    # Same deck
    # -------------------------------------------------

    decks = {
        seat["upper_lower"]
        for seat in seats
    }

    score = 0

    if len(decks) == 1:
        score += 100

    # -------------------------------------------------
    # Number of rows occupied
    # -------------------------------------------------

    rows = {
        seat["row"]
        for seat in seats
    }

    row_count = len(rows)

    if row_count == 1:
        score += 300

    elif row_count == 2:
        score += 200

    elif row_count == 3:
        score += 100

    else:
        score -= (row_count - 3) * 50

       # -------------------------------------------------
    # Same-row grouping
    # -------------------------------------------------

    row_groups = defaultdict(list)

    for seat in seats:
        row_groups[seat["row"]].append(seat)

    row_sizes = []

    for row_seats in row_groups.values():

        count = len(row_seats)

        row_sizes.append(count)

        # Strong bonus for seats sharing the same row.
        if count == 2:
            score += 180

        elif count == 3:
            score += 400

        elif count > 3:
            score += 400 + (count - 3) * 100

    # -------------------------------------------------
    # Reward larger groups over fragmented groups
    # -------------------------------------------------

    row_sizes.sort(reverse=True)

    for index, size in enumerate(row_sizes):

        if index == 0:
            score += size * 50

        elif index == 1:
            score += size * 30

        else:
            score += size * 10

    # -------------------------------------------------
    # Distance between seats
    # -------------------------------------------------

    total_distance = 0

    for i in range(len(seats)):

        for j in range(i + 1, len(seats)):

            total_distance += seat_distance(
                seats[i],
                seats[j],
            )

    score -= total_distance * 5

    return score


def calculate_group_score(
    seats: list[dict],
    *,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
) -> float:

    score = 0

    # Togetherness is the primary objective.
    score += group_togetherness_score(seats)

    # Customer preferences.
    for seat in seats:

        score += preference_score(
            seat,
            window=window,
            aisle=aisle,
            lower=lower,
            upper=upper,
            front=front,
            rear=rear,
            sleeper=sleeper,
            seater=seater,
        )

    # Slight price preference.
    total_price = sum(
        seat["price"]
        for seat in seats
    )

    score -= total_price * 0.02

    return score


def find_best_group(
    seats: list[dict],
    passengers: int,
    *,
    window: bool = False,
    aisle: bool = False,
    lower: bool = False,
    upper: bool = False,
    front: bool = False,
    rear: bool = False,
    sleeper: bool = False,
    seater: bool = False,
) -> dict:

    available = [
        seat
        for seat in seats
        if seat.get("status") == "available"
    ]

    if len(available) < passengers:

        return {
            "success": False,
            "reason": (
                f"Only {len(available)} seats are available "
                f"for {passengers} passengers."
            ),
        }

    if passengers < 1 or passengers > 10:

        return {
            "success": False,
            "reason": (
                "The supported group size is "
                "between 1 and 10 passengers."
            ),
        }

    # -------------------------------------------------
    # Build lookup and graph
    # -------------------------------------------------

    seat_by_id = {
        seat["id"]: seat
        for seat in available
    }

    graph = build_adjacency_graph(available)

    # -------------------------------------------------
    # Candidate groups
    # -------------------------------------------------

    candidates = []

    # Start a candidate group from every seat.
    for start_seat in available:

        group = [start_seat]

        visited = {
            start_seat["id"]
        }

        frontier = [
            start_seat["id"]
        ]

        while frontier and len(group) < passengers:

            current_id = frontier.pop(0)

            neighbours = graph.get(
                current_id,
                set(),
            )

            # Sort neighbours by physical distance.
            sorted_neighbours = sorted(
                neighbours,
                key=lambda seat_id: seat_distance(
                    seat_by_id[current_id],
                    seat_by_id[seat_id],
                ),
            )

            for neighbour_id in sorted_neighbours:

                if neighbour_id in visited:
                    continue

                visited.add(neighbour_id)

                group.append(
                    seat_by_id[neighbour_id]
                )

                frontier.append(
                    neighbour_id
                )

                if len(group) >= passengers:
                    break

        if len(group) == passengers:
            candidates.append(group)

    # -------------------------------------------------
    # Fallback
    # -------------------------------------------------

    if not candidates:

        # If no connected group exists, select the seats
        # closest to the starting seat.
        for start_seat in available:

            others = [
                seat
                for seat in available
                if seat["id"] != start_seat["id"]
            ]

            others.sort(
                key=lambda seat: seat_distance(
                    start_seat,
                    seat,
                )
            )

            group = [
                start_seat,
                *others[: passengers - 1],
            ]

            candidates.append(group)

    # -------------------------------------------------
    # Find highest scoring group
    # -------------------------------------------------

    best_group = max(
        candidates,
        key=lambda group: calculate_group_score(
            group,
            window=window,
            aisle=aisle,
            lower=lower,
            upper=upper,
            front=front,
            rear=rear,
            sleeper=sleeper,
            seater=seater,
        ),
    )

    score = calculate_group_score(
        best_group,
        window=window,
        aisle=aisle,
        lower=lower,
        upper=upper,
        front=front,
        rear=rear,
        sleeper=sleeper,
        seater=seater,
    )

    return {
        "success": True,
        "score": round(score, 2),

        "seat_ids": [
            seat["id"]
            for seat in best_group
        ],

        "seat_numbers": [
            seat["seat_number"]
            for seat in best_group
        ],

        "total_price": sum(
            seat["price"]
            for seat in best_group
        ),

        "seats": best_group,
    }