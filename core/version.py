import os

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

VERSION_FILE = os.path.join(
    BASE_DIR,
    "VERSION"
)


def get_version():
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()

    except FileNotFoundError:
        return "unknown"
