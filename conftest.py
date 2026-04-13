"""Root conftest: load .env before any test collection.

Mirrors PyCharm's "Paths to .env files" feature — injects .env vars into the
process environment before pytest collects tests. Path is anchored to this
file's location so it works regardless of the working directory pytest is
invoked from.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
