import hashlib
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .budget import Budget


MAX_JSON_BYTES = 12 * 1024 * 1024
USER_AGENT = "SignalPost/2.0 (+https://builderr.ai/challenges/signalpost)"
BRREG = "https://data.brreg.no"


@dataclass
class Fetch:
    url: str
    status: int
    body: Any
    raw: bytes
    retrieved_at: str
    error: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class HttpClient:
    def __init__(self, budget: Budget, timeout: float = 12.0):
        self.budget = budget
        self.timeout = timeout

    def json(self, url: str) -> Fetch:
        if not url.startswith(BRREG + "/"):
            raise ValueError("Only allowlisted BRREG URLs are accepted by the official connector")
        self.budget.reserve()
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        stamp = now()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                length = int(response.headers.get("Content-Length") or 0)
                if length > MAX_JSON_BYTES:
                    return Fetch(url, 413, None, b"", stamp, "response exceeds safety limit")
                raw = response.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    return Fetch(url, 413, None, b"", stamp, "response exceeds safety limit")
                return Fetch(response.geturl(), response.status, json.loads(raw.decode("utf-8")), raw, stamp)
        except urllib.error.HTTPError as exc:
            return Fetch(url, exc.code, None, b"", stamp, f"HTTP {exc.code}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            return Fetch(url, 0, None, b"", stamp, type(exc).__name__)


def official_urls(orgnr: str) -> dict[str, str]:
    base = f"{BRREG}/enhetsregisteret/api/enheter/{orgnr}"
    return {
        "registry": base,
        "roles": base + "/roller",
        "financials": f"{BRREG}/regnskapsregisteret/regnskap/{orgnr}",
        "group": f"{BRREG}/enhetsregisteret/api/konsernstruktur/{orgnr}",
        "locations": f"{BRREG}/enhetsregisteret/api/underenheter?overordnetEnhet={orgnr}&size=1000",
    }

