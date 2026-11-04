import unittest
from http.client import RemoteDisconnected
from unittest.mock import MagicMock, patch

from signalpost.budget import Budget
from signalpost.sources import BRREG, HttpClient


class SourceTransportTests(unittest.TestCase):
    def test_official_json_retries_a_remote_disconnect(self):
        url = BRREG + "/enhetsregisteret/api/enheter/923609016"
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers.get.return_value = "2"
        response.read.return_value = b"{}"
        response.geturl.return_value = url
        response.status = 200
        budget = Budget(max_requests=3)
        with patch("signalpost.sources.urllib.request.urlopen", side_effect=[RemoteDisconnected("closed"), response]) as opener:
            fetched = HttpClient(budget).json(url)
        self.assertEqual(fetched.status, 200)
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(budget.requests, 2)

    def test_company_page_disconnect_returns_failed_fetch(self):
        url = "https://example.no/"
        opener = MagicMock()
        opener.open.side_effect = RemoteDisconnected("closed")
        with patch("signalpost.sources.safe_public_url"), patch("signalpost.sources.urllib.request.build_opener", return_value=opener):
            fetched = HttpClient(Budget(max_requests=1)).text(url)
        self.assertEqual(fetched.status, 0)
        self.assertEqual(fetched.error, "RemoteDisconnected")


if __name__ == "__main__":
    unittest.main()
