import sys
from pathlib import Path

# Add project root to sys.path so it works when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

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