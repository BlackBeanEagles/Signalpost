import json
import tempfile
import unittest
from pathlib import Path

from signalpost.validate import validate_jsonl


class ValidateTests(unittest.TestCase):
    def test_valid_profile(self):
        profile = {
            "organization_number": "923609016",
            "legal_name": "EQUINOR ASA",
            "facts": [{
                "field": "legal_name",
                "value": "EQUINOR ASA",
                "confidence": 1.0,
                "evidence": {
                    "source_name": "BRREG",
                    "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
                    "retrieved_at": "2026-10-12T00:00:00Z",
                    "json_path": "$.navn"
                }
            }]
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "profiles.jsonl"
            path.write_text(json.dumps(profile) + "\n", encoding="utf-8")
            report = validate_jsonl(path, minimum=1)
        self.assertTrue(report["valid"])
        self.assertEqual(report["unique_organization_numbers"], 1)


if __name__ == "__main__":
    unittest.main()
