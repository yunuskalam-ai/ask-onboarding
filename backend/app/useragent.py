"""Turn a browser's User-Agent string into "Chrome 131", "Windows", "Desktop".

A handful of ordered patterns covers the browsers people actually use; order
matters because browsers borrow each other's names (Edge says "Chrome" and
"Safari", an iPad says "Mac OS X"). Anything unrecognised is None, shown as a
dash, never guessed. The raw string is kept in the audit log, so these rules
can improve later without losing anything.
"""

import re
from dataclasses import dataclass

_BROWSERS = [
    ("Edge", r"Edg(?:e|A|iOS)?/(\d+)"),
    ("Opera", r"OPR/(\d+)"),
    ("Samsung Internet", r"SamsungBrowser/(\d+)"),
    ("Chrome", r"(?:Chrome|CriOS)/(\d+)"),
    ("Firefox", r"(?:Firefox|FxiOS)/(\d+)"),
    ("Safari", r"Version/(\d+)[\d.]*(?: Mobile/\S+)? Safari/"),
    ("curl", r"^curl/(\d+)"),
    ("Python", r"^(?:python-requests|python-httpx|Python-urllib)/(\d+)"),
]
_SCRIPTS = {"curl", "Python"}

_SYSTEMS = [
    ("iOS", r"(?:iPhone|iPad|iPod).*? OS (\d+)"),
    ("Android", r"Android (\d+)"),
    ("Windows", r"Windows NT"),  # Windows 10 and 11 both say "NT 10.0", so no version
    ("ChromeOS", r"CrOS"),
    ("macOS", r"Mac OS X"),
    ("Linux", r"Linux"),
]


@dataclass(frozen=True)
class Device:
    browser: str | None  # "Chrome 131"
    os: str | None  # "Android 15", "Windows"
    kind: str | None  # "Desktop", "Phone", "Tablet" or "Script"


def _first(rules: list[tuple[str, str]], text: str) -> tuple[str, str | None] | None:
    for name, pattern in rules:
        if match := re.search(pattern, text):
            return name, next((g for g in match.groups() if g), None)
    return None


def describe(user_agent: str | None) -> Device:
    if not user_agent:
        return Device(None, None, None)
    browser = _first(_BROWSERS, user_agent)
    system = _first(_SYSTEMS, user_agent)
    if browser and browser[0] in _SCRIPTS:
        kind = "Script"
    elif "iPad" in user_agent or (system and system[0] == "Android" and "Mobile" not in user_agent):
        kind = "Tablet"
    elif re.search(r"Mobi|iPhone", user_agent):
        kind = "Phone"
    elif system:
        kind = "Desktop"
    else:
        kind = None
    return Device(
        " ".join(p for p in browser if p) if browser else None,
        " ".join(p for p in system if p) if system else None,
        kind,
    )
