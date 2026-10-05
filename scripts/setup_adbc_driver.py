"""Download and verify the Linux x86_64 ADBC driver at VASTDB_ADBC_DRIVER_PATH."""

import ctypes
import hashlib
import io
import os
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

DRIVER_URL = (
    "https://github.com/vast-data/vastdb-adbc-driver/releases/download/v0.0.32/"
    "vastdb-adbc-driver-v0.0.32-linux-x86_64.zip"
)
EXPECTED_SHA256 = "038b70a5b0843e6ae5c9802654fd0923c711d2360af1f34e4f33573c3dabd0fd"
DRIVER_MEMBER = "vastdb-adbc-driver-v0.0.32-linux-x86_64/libadbc_driver_vastdb.so"

driver = Path(os.environ["VASTDB_ADBC_DRIVER_PATH"])
with urlopen(DRIVER_URL, timeout=30) as response:
    archive = response.read(6 * 1024 * 1024)
if hashlib.sha256(archive).hexdigest() != EXPECTED_SHA256:
    raise SystemExit("VAST ADBC driver checksum mismatch")
driver.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(io.BytesIO(archive)) as bundle:
    driver.write_bytes(bundle.read(DRIVER_MEMBER))
ctypes.CDLL(str(driver)).AdbcDriverInit
print("VAST ADBC driver v0.0.32 loaded")
