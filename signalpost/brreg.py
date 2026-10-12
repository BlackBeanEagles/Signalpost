import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .budget import Budget


BASE_URL = "https://data.brreg.no/enhetsregisteret/api"
ACCEPT = "application/vnd.brreg.enhetsregisteret.enhet.v2+json"
USER_AGENT = "SignalPost/1.0 (hackathon research agent)"


class SourceError(RuntimeError):
    pass


@dataclass
class BrregClient:
    budget: Budget
    timeout: float = 20.0
    retries: int = 2

    def _get(self, url: str, accept: str = ACCEPT) -> dict:
        last_error = None
        for attempt in range(self.retries + 1):
            self.budget.reserve(1, 0.0)
            request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 404, 410):
                    raise SourceError(f"BRREG returned HTTP {exc.code} for {url}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.25 * (2**attempt))
        raise SourceError(f"BRREG request failed for {url}: {last_error}")

    def entity(self, orgnr: str) -> tuple[dict, str]:
        url = f"{BASE_URL}/enheter/{urllib.parse.quote(orgnr)}"
        return self._get(url), url

    def roles(self, orgnr: str) -> tuple[dict, str]:
        url = f"{BASE_URL}/enheter/{urllib.parse.quote(orgnr)}/roller"
        return self._get(url, "application/vnd.brreg.enhetsregisteret.rolle.v1+json"), url

    def entity_page(self, page: int, size: int = 100) -> dict:
        query = urllib.parse.urlencode({"page": page, "size": size, "sort": "organisasjonsnummer,ASC"})
        return self._get(f"{BASE_URL}/enheter?{query}")

