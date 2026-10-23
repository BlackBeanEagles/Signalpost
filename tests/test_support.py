import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from signalpost.budget import Budget
from signalpost.support import attach_support, fetch_support_awards


class FakeResponse:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        raw, self.raw = self.raw, b""
        return raw


class SupportTests(unittest.TestCase):
    def test_partial_utf16_download_keeps_only_complete_exact_recipient_rows(self):
        awarded = (datetime.now(timezone.utc).date() - timedelta(days=7)).strftime("%d.%m.%Y")
        header = '"Støttetiltaksnummer";"Organisasjonsnummer støttemottaker";"Tildelingsdato";"Tildelt beløp";"Tildelt beløp valuta";"Navn støttemottaker";"Navn støttegiver"\r\n'
        good = f'"1001";"923609016";"{awarded}";"1 234,50";"NOK";"EQUINOR ASA";"ENOVA SF"\r\n'
        wrong = f'"1002";"914778271";"{awarded}";"9 999,00";"NOK";"ANOTHER AS";"ENOVA SF"\r\n'
        raw = (header + good + wrong + '"1003";"923609016";"').encode("utf-16-le")
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            with patch("signalpost.support.urllib.request.urlopen", return_value=FakeResponse(raw)), patch("signalpost.support.time.perf_counter", side_effect=[0, 0, 31, 31]):
                awards, metadata = fetch_support_awards({"923609016"}, Budget(), Path(directory), total_timeout=30)
        self.assertEqual(metadata["status"], "partial")
        self.assertFalse(metadata["complete_snapshot"])
        self.assertEqual(metadata["claims"], 1)
        self.assertEqual(awards["923609016"][0]["value"]["amount"], "1234.50")
        self.assertEqual(awards["923609016"][0]["value"]["support_measure_number"], "1001")
        row = {"organisation_number": "923609016", "claims": [], "evidence": []}
        attach_support(row, awards["923609016"], metadata)
        self.assertFalse(row["evidence"][0]["source_snapshot_complete"])
        self.assertEqual(row["claims"][0]["field"], "official.support_award")

    def test_complete_download_is_marked_complete(self):
        awarded = datetime.now(timezone.utc).date().strftime("%d.%m.%Y")
        raw = ('"Organisasjonsnummer støttemottaker";"Tildelingsdato";"Tildelt beløp"\r\n'
               f'"923609016";"{awarded}";"0"\r\n').encode("utf-16-le")
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            with patch("signalpost.support.urllib.request.urlopen", return_value=FakeResponse(raw)):
                awards, metadata = fetch_support_awards({"923609016"}, Budget(), Path(directory), total_timeout=30)
        self.assertEqual(metadata["status"], "available")
        self.assertTrue(metadata["complete_snapshot"])
        self.assertEqual(awards["923609016"][0]["value"]["amount"], "0")


if __name__ == "__main__":
    unittest.main()
