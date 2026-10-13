import hashlib
import json
import socket
import ipaddress
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .budget import Budget


MAX_JSON_BYTES = 12 * 1024 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
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
        self.requests = 0

    def _reserve(self) -> None:
        self.budget.reserve()
        self.requests += 1

    def json(self, url: str) -> Fetch:
        if not url.startswith(BRREG + "/"):
            raise ValueError("Only allowlisted BRREG URLs are accepted by the official connector")
        self._reserve()
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

    def text(self, url: str) -> Fetch:
        safe_public_url(url)
        self._reserve()
        request = urllib.request.Request(url, headers={"Accept": "text/html,application/xhtml+xml,text/plain;q=0.8", "User-Agent": USER_AGENT})
        stamp = now()
        try:
            opener = urllib.request.build_opener(_SafeRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if not any(item in content_type for item in ("text/html", "application/xhtml", "text/plain")):
                    return Fetch(response.geturl(), 415, None, b"", stamp, "unsupported content type")
                length = int(response.headers.get("Content-Length") or 0)
                if length > MAX_HTML_BYTES:
                    return Fetch(response.geturl(), 413, None, b"", stamp, "response exceeds safety limit")
                raw = response.read(MAX_HTML_BYTES + 1)
                if len(raw) > MAX_HTML_BYTES:
                    return Fetch(response.geturl(), 413, None, b"", stamp, "response exceeds safety limit")
                charset = response.headers.get_content_charset() or "utf-8"
                return Fetch(response.geturl(), response.status, raw.decode(charset, errors="replace"), raw, stamp)
        except urllib.error.HTTPError as exc:
            return Fetch(url, exc.code, None, b"", stamp, f"HTTP {exc.code}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError) as exc:
            return Fetch(url, 0, None, b"", stamp, type(exc).__name__)


def safe_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsafe website URL")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("nonstandard website port")
    for result in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError("website resolves to a non-public address")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def official_urls(orgnr: str) -> dict[str, str]:
    base = f"{BRREG}/enhetsregisteret/api/enheter/{orgnr}"
    return {
        "registry": base,
        "roles": base + "/roller",
        "financials": f"{BRREG}/regnskapsregisteret/regnskap/{orgnr}",
        "group": f"{BRREG}/enhetsregisteret/api/konsernstruktur/{orgnr}",
        "locations": f"{BRREG}/enhetsregisteret/api/underenheter?overordnetEnhet={orgnr}&size=1000",
    }

