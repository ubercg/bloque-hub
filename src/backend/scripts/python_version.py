#!/usr/bin/env python
import sys
from datetime import datetime


def main():
    print(f"Python version: {sys.version}")
    print(f"Current datetime: {datetime.now()}")


if __name__ == "__main__":
    main()