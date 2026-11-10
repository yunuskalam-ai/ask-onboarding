"""The audit log's context: the client's IP, where it is, and its browser, system and device."""

import gzip
import io
import os
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import auth, geoip
from app.client_info import client_ip
from app.deps import get_database_url
from app.main import app
from app.useragent import Device, describe
from tests.conftest import add_user, sign_in_as

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# --- Browser, system and device --------------------------------------------------------


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (CHROME_WINDOWS, Device("Chrome 131", "Windows", "Desktop")),
        (CHROME_WINDOWS + " Edg/131.0.2903.86", Device("Edge 131", "Windows", "Desktop")),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
            Device("Safari 18", "macOS", "Desktop"),
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
            Device("Safari 18", "iOS 18", "Phone"),
        ),
        (
            "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) CriOS/130.0 Mobile/15E148 Safari/604.1",
            Device("Chrome 130", "iOS 17", "Tablet"),
        ),
        (
            "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            Device("Chrome 131", "Android 15", "Phone"),
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36"
            " (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Safari/537.36",
            Device("Samsung Internet 26", "Android 14", "Tablet"),
        ),
        (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
            Device("Firefox 133", "Linux", "Desktop"),
        ),
        ("curl/8.9.1", Device("curl 8", None, "Script")),
        ("python-requests/2.32.3", Device("Python 2", None, "Script")),
        ("something unheard of", Device(None, None, None)),
        ("", Device(None, None, None)),
        (None, Device(None, None, None)),
    ],
)
def test_describe_reads_common_browsers_and_never_guesses(user_agent, expected):
    assert describe(user_agent) == expected


# --- The client's IP ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("peer", "header", "expected"),
    [
        ("172.18.0.5", "94.200.12.7", "94.200.12.7"),  # from our proxy: believed
        ("127.0.0.1", "2a02:6b8::1", "2a02:6b8::1"),
        ("172.18.0.5", None, "172.18.0.5"),  # no header: the peer
        ("172.18.0.5", "not an ip", "172.18.0.5"),  # junk header: ignored
        ("94.200.12.7", "1.2.3.4", "94.200.12.7"),  # NEGATIVE: a public client can't name another IP
        ("testclient", "1.2.3.4", None),  # not an address at all
        (None, "1.2.3.4", None),
    ],
)
def test_client_ip_believes_x_real_ip_only_from_a_private_peer(peer, header, expected):
    assert client_ip(peer, header) == expected


# --- Location ------------------------------------------------------------------------------


class FakeReader:
    def get(self, ip):
        if ip != "94.200.12.7":
            return None
        return {"city": {"names": {"en": "Dubai"}}, "country": {"names": {"en": "United Arab Emirates"}}}


def test_location_names_city_and_country(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip, "_reader", lambda path: FakeReader())
    assert geoip.location("94.200.12.7", tmp_path / "db.mmdb") == "Dubai, United Arab Emirates"
    assert geoip.location("8.8.4.4", tmp_path / "db.mmdb") is None  # not in the database


@pytest.mark.parametrize("ip", ["10.1.2.3", "192.168.1.20", "127.0.0.1", "::1", "fe80::1"])
def test_office_and_local_addresses_are_a_private_network_without_any_database(ip, tmp_path):
    assert geoip.location(ip, tmp_path / "missing.mmdb") == geoip.PRIVATE


@pytest.mark.parametrize("ip", [None, "", "not an ip"])
def test_no_or_bad_ip_has_no_location(ip, tmp_path):
    assert geoip.location(ip, tmp_path / "missing.mmdb") is None


def test_no_database_means_no_location_not_an_error(tmp_path):
    assert geoip.location("94.200.12.7", tmp_path / "missing.mmdb") is None


def test_a_damaged_database_means_no_location_not_an_error(tmp_path):
    damaged = tmp_path / "damaged.mmdb"
    damaged.write_bytes(b"this is not a database")
    assert geoip.location("94.200.12.7", damaged) is None


# --- Keeping the database fresh -------------------------------------------------------------


def _gz(data: bytes):
    return lambda url: io.BytesIO(gzip.compress(data))


def test_a_fresh_database_is_not_downloaded_again(tmp_path):
    path = tmp_path / "db.mmdb"
    path.write_bytes(b"current")

    def fail(url):
        raise AssertionError("should not download")

    assert geoip.refresh(path, opener=fail) is False


def test_a_missing_database_is_downloaded_falling_back_to_last_month(tmp_path, monkeypatch):
    monkeypatch.setattr(geoip.maxminddb, "open_database", lambda p: io.BytesIO())  # accept the stand-in
    tried = []

    def opener(url):
        tried.append(url)
        if "2027-01" in url:
            raise OSError("404: not published yet")
        return io.BytesIO(gzip.compress(b"december's database"))

    path = tmp_path / "geoip" / "db.mmdb"
    assert geoip.refresh(path, today=date(2027, 1, 1), opener=opener) is True
    assert tried == [geoip.URL.format(year=2027, month=1), geoip.URL.format(year=2026, month=12)]
    assert path.read_bytes() == b"december's database"
    assert not path.with_suffix(".partial").exists()


def test_a_bad_download_leaves_the_old_database_in_place(tmp_path):
    """NEGATIVE: junk that isn't a database is refused; the working file stays."""
    path = tmp_path / "db.mmdb"
    path.write_bytes(b"the old, working database")
    month_old = time.time() - 40 * 86400
    os.utime(path, (month_old, month_old))
    with pytest.raises(RuntimeError, match="Could not download"):
        geoip.refresh(path, today=date(2026, 11, 10), opener=_gz(b"<html>Error</html>"))
    assert path.read_bytes() == b"the old, working database"
    assert not path.with_suffix(".partial").exists()


# --- End to end: through the API -------------------------------------------------------------


def _client(test_database_url, peer):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    return TestClient(app, client=(peer, 50000))


def _sign_in_entry(client, admin_client, email):
    client.post(
        "/api/auth/sign-in", json={"email": email}, headers={"User-Agent": CHROME_WINDOWS, "X-Real-IP": "94.200.12.7"}
    )
    entries = admin_client.get("/api/admin/audit").json()
    return next(e for e in entries if e["action"] == "sign_in" and e["actor"] != "Admin Person")


def test_the_audit_log_records_ip_location_browser_system_and_device(db, test_database_url, monkeypatch):
    monkeypatch.setattr(geoip, "_reader", lambda path: FakeReader())
    try:
        admin_client = _client(test_database_url, "172.18.0.5")
        sign_in_as(admin_client, db, "admin", "Admin Person")
        person = add_user(db, "employee", "Sam")
        entry = _sign_in_entry(_client(test_database_url, "172.18.0.5"), admin_client, person.email)
    finally:
        app.dependency_overrides.clear()
    assert entry["ip"] == "94.200.12.7"
    assert entry["location"] == "Dubai, United Arab Emirates"
    assert (entry["browser"], entry["os"], entry["device"]) == ("Chrome 131", "Windows", "Desktop")


def test_a_client_reaching_the_api_directly_cannot_fake_its_ip(db, test_database_url):
    """NEGATIVE: X-Real-IP from a public address is ignored; the real peer is recorded."""
    try:
        admin_client = _client(test_database_url, "172.18.0.5")
        sign_in_as(admin_client, db, "admin", "Admin Person")
        person = add_user(db, "employee", "Sam")
        entry = _sign_in_entry(_client(test_database_url, "8.8.8.8"), admin_client, person.email)
    finally:
        app.dependency_overrides.clear()
    assert entry["ip"] == "8.8.8.8"
    assert entry["location"] is None  # no database in tests (conftest)


def test_entries_written_outside_a_request_have_no_client(db, test_database_url):
    auth.record(db, None, "system.job")
    row = db.execute("SELECT ip, location, user_agent FROM audit_log WHERE action = 'system.job'").fetchone()
    assert row == {"ip": None, "location": None, "user_agent": None}
