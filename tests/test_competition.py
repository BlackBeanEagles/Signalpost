import json
import tempfile
import unittest
from pathlib import Path

from signalpost.competition import read_inputs
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

    def test_reads_frozen_bulk_identity(self):
        records, digest = read_bulk_selected(Path("tests/fixtures/brreg-sample.csv"), {"923609016"})
        self.assertEqual(records["923609016"]["navn"], "EQUINOR ASA")
        self.assertEqual(records["923609016"]["organisasjonsform"]["kode"], "ASA")
        self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()

