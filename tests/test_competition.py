import json
import tempfile
import unittest
from pathlib import Path

from signalpost.competition import plan_modules, read_inputs
from signalpost.evaluator import validate_envelopes
from signalpost.bulk import read_bulk_selected


class CompetitionTests(unittest.TestCase):
    def test_reads_builderr_jsonl(self):
        path = Path("tests/fixtures/smoke-organisations.jsonl")
        self.assertEqual(read_inputs(path), ["923609016", "914778271"])

    def test_duplicate_inputs_fail(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text('{"organisation_number":"923609016"}\n{"organisation_number":"923609016"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_inputs(path)

    def test_normalizes_formatted_organisation_number(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text('{"organisation_number":"923 609 016"}\n', encoding="utf-8")
            self.assertEqual(read_inputs(path), ["923609016"])

    def test_rejects_invalid_organisation_number(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.txt"
            path.write_text("123\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_inputs(path)

    def test_reads_frozen_bulk_identity(self):
        records, digest = read_bulk_selected(Path("tests/fixtures/brreg-sample.csv"), {"923609016"})
        self.assertEqual(records["923609016"]["navn"], "EQUINOR ASA")
        self.assertEqual(records["923609016"]["organisasjonsform"]["kode"], "ASA")
        self.assertEqual(len(digest), 64)

    def test_current_official_scale_keeps_high_value_modules(self):
        modules, pages = plan_modules(1500, 15000, True)
        self.assertEqual(modules, {"registry", "financials", "roles", "website", "locations", "group"})
        self.assertEqual(pages, 5)


if __name__ == "__main__":
    unittest.main()

