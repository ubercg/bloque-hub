"""Utility script that prints the current Python version and datetime.

Usage:
    python scripts/python_version.py

No external dependencies or project imports required.
"""

import sys
from datetime import datetime


def main() -> None:
    """Print the current Python version and the current datetime to stdout."""
    print(f"Python version: {sys.version}")
    print(f"Current datetime: {datetime.now()}")


if __name__ == "__main__":
    main()