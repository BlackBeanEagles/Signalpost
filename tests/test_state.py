import tempfile
import unittest
from pathlib import Path

from signalpost.state import StateStore


class StateTests(unittest.TestCase):
    def test_idempotent_and_tracks_add_update_remove(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            evidence = [{"source_url": "https://data.brreg.no/x", "content_sha256": "a" * 64, "retrieved_at": "t1"}]
            first = [{"key": "a", "value": 1, "availability": "available", "evidence_ids": ["ev1"]}]
            self.assertEqual(store.apply("923609016", first, evidence, "t1"), [])
            self.assertEqual(store.apply("923609016", first, evidence, "t2"), [])
            second = [
                {"key": "a", "value": 2, "availability": "available", "evidence_ids": ["ev2"]},
                {"key": "b", "value": 3, "availability": "available", "evidence_ids": ["ev2"]},
            ]
            changes = store.apply("923609016", second, evidence, "t3")
            self.assertEqual({item["change_type"] for item in changes}, {"updated", "added"})
            changes = store.apply("923609016", [second[1]], evidence, "t4")
            self.assertEqual([item["change_type"] for item in changes], ["removed"])
            store.close()


if __name__ == "__main__":
    unittest.main()
