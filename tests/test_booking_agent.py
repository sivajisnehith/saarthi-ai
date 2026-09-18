from agent.agent import saarthi


def main():

    print("\n========================================")
    print("       SAARTHI BOOKING AGENT TEST")
    print("========================================\n")

    print("Type 'exit' to stop.\n")

    while True:

        user_input = input("Customer: ").strip()

        # Ignore empty input.
        if not user_input:
            print("Please enter a message.\n")
            continue

        if user_input.lower() == "exit":
            print("\nExiting Saarthi...")
            break

        print("\nSaarthi:\n")

        try:

            response = saarthi(user_input)

            print(response)

        except Exception as e:

            print("\nERROR:")
            print(e)

        print("\n" + "-" * 50 + "\n")


if __name__ == "__main__":
    main()