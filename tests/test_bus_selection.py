import sys
from pathlib import Path

# Add project root to sys.path so it works when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from agent.agent import saarthi


def main():

    print("Saarthi bus selection test...\n")

    response = saarthi(
        """
        Customer conversation:

        Customer:
        I need to travel from Hyderabad to Vijayawada
        on 2026-09-18 for 4 passengers.
        I want sleeper seats.

        Saarthi:
        [Search the buses and show me the available options.]

        Customer:
        I'll take Bus ID 11.
        Now find the best 4 seats together for us.

        Continue the conversation from here.
        Use the appropriate tool to find the group seats.
        """
    )

    print("\n==============================")
    print("SAARTHI RESPONSE")
    print("==============================\n")

    print(response)


if __name__ == "__main__":
    main()