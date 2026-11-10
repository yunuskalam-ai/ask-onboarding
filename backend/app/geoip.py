"""Where an IP address is: "Dubai, United Arab Emirates". Looked up offline.

The city database is DB-IP's free "IP to City Lite" (CC BY 4.0: the Overview
credits it). It lives on the api container's `geoip` volume and is downloaded
on start when missing or older than 30 days; DB-IP publishes a new one monthly.
No IP address is ever sent anywhere to be looked up.

Everything here is best-effort: with no database a location is simply None,
and the audit log still records the IP.
"""

import gzip
import logging
import os
import shutil
import time
from collections.abc import Callable
from datetime import date
from ipaddress import ip_address
from pathlib import Path
from typing import IO, Any
from urllib.request import Request, urlopen

import maxminddb

log = logging.getLogger(__name__)

URL = "https://download.db-ip.com/free/dbip-city-lite-{year}-{month:02d}.mmdb.gz"
MAX_AGE_DAYS = 30
# DB-IP refuses Python's default User-Agent (403), so name the client.
USER_AGENT = "ask-onboarding (+https://github.com/yunuskalam-ai/ask-onboarding)"
PRIVATE = "Private network"

_cache: dict[str, Any] = {"path": None, "mtime": None, "reader": None}


def _reader(path: Path) -> Any:
    """The open database, reopened when the file changes; None if there is none."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    if _cache["path"] != path or _cache["mtime"] != mtime:
        _cache.update(path=path, mtime=mtime, reader=maxminddb.open_database(str(path)))
    return _cache["reader"]


def location(ip: str | None, path: Path) -> str | None:
    """ "City, Country", "Private network" for office and local addresses, or None if unknown."""
    try:
        address = ip_address(ip) if ip else None
    except ValueError:
        return None
    if address is None:
        return None
    if address.is_private or address.is_loopback or address.is_link_local:
        return PRIVATE
    try:
        reader = _reader(path)
        record = reader.get(str(address)) if reader else None
    except Exception:  # a damaged file must never break sign-in
        log.exception("Looking up %s in %s failed", address, path)
        return None
    if not isinstance(record, dict):
        return None
    names = [record.get(part, {}).get("names", {}).get("en") for part in ("city", "country")]
    return ", ".join(n for n in names if n) or None


def _months_to_try(today: date) -> list[date]:
    """This month's file, then last month's (the new one appears a day or two in)."""
    last = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    return [today.replace(day=1), last]


def refresh(path: Path, today: date | None = None, opener: Callable[[str], IO[bytes]] | None = None) -> bool:
    """Download the database if it is missing or old. True if a new one was installed.

    The download goes to a temporary file first and replaces the old one only
    when complete, so a failure halfway leaves the working database in place.
    """
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_DAYS * 86400:
        return False
    today = today or date.today()
    opener = opener or (lambda url: urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60))  # noqa: S310  # fixed https URL above
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    last_error: Exception | None = None
    for month in _months_to_try(today):
        url = URL.format(year=month.year, month=month.month)
        try:
            with opener(url) as response, gzip.open(response) as unzipped, partial.open("wb") as out:
                shutil.copyfileobj(unzipped, out)
            maxminddb.open_database(str(partial)).close()  # refuse a file that isn't a database
        except Exception as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            continue
        os.replace(partial, path)
        log.info("Installed the IP location database from %s", url)
        return True
    raise RuntimeError(f"Could not download the IP location database: {last_error}")
