"""CirClock entry point — double-click this file (no console window)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cirtimer.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
