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
        I'll take Bus ID 11.
        Find 4 seats together for us.
        """
    )

    print("\nSaarthi:")
    


if __name__ == "__main__":
    main()