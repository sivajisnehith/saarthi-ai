from agent.agent import saarthi


def main():

    print("Saarthi is starting...\n")

    response = saarthi(
        """
        I need to travel from Hyderabad to Vijayawada on 2026-09-18
        for 2 passengers.

        Find me buses for the journey. I prefer sleeper buses at night.

        Once you find the buses, I want cheap window sleeper seats.
        Show me the best seat options.
        """
    )

    print("\nSaarthi:")
    print(response)


if __name__ == "__main__":
    main()