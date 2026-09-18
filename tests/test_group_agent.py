from agent.agent import saarthi


def main():

    print("Saarthi group seating test...\n")

    response = saarthi(
        """
        I need to travel from Hyderabad to Vijayawada
        on 2026-09-18 for 4 passengers.

        Find me suitable buses.

        We are travelling together, so I want 4 seats
        as close together as possible.

        Prefer sleeper seats.
        """
    )

    print("\n==============================")
    print("SAARTHI RESPONSE")
    print("==============================\n")

    print(response)


if __name__ == "__main__":
    main()