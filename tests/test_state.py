import tempfile
import unittest
from pathlib import Path

from signalpost.state import StateStore


class StateTests(unittest.TestCase):
    def test_partial_or_blocked_sources_do_not_create_false_removals(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            original = [
                {"key": "company.phone", "value": "12345678", "availability": "available", "evidence_ids": ["registry"]},
                {"key": "people.official_role:chair", "value": {"name": "A"}, "availability": "available", "evidence_ids": ["roles"]},
                {"key": "website.official", "value": "https://example.no", "availability": "available", "evidence_ids": ["site"]},
                {"key": "official.support_award:one", "value": {"amount": 1}, "availability": "available", "evidence_ids": ["support"]},
            ]
            store.apply("923609016", original, [], "t1", source_snapshots=[])
            snapshots = [
                {"source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016", "status": 200},
                {"source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016/roller", "status": 429},
            ]
            changes = store.apply("923609016", [], [], "t2", source_snapshots=snapshots, support_snapshot_complete=False)
            self.assertEqual([(item["claim_key"], item["change_type"]) for item in changes], [("company.phone", "removed")])
            self.assertEqual(store.apply("923609016", [], [], "t3", source_snapshots=snapshots, support_snapshot_complete=False), [])
            recovered = snapshots[:1] + [{"source_url": snapshots[1]["source_url"], "status": 200}]
            changes = store.apply("923609016", [], [], "t4", source_snapshots=recovered, support_snapshot_complete=True)
            self.assertEqual({item["claim_key"] for item in changes}, {"people.official_role:chair", "official.support_award:one"})
            store.close()

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
