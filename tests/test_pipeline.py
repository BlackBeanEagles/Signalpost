import unittest

from signalpost.pipeline import facts_from_entity


class PipelineTests(unittest.TestCase):
    def test_empty_values_are_not_published(self):
        payload = {"organisasjonsnummer": "923609016", "navn": "EQUINOR ASA", "telefon": ""}
        fields = {fact.field for fact in facts_from_entity(payload, "https://example.test", "2026-10-12T00:00:00Z")}
        self.assertIn("legal_name", fields)
        self.assertNotIn("phone", fields)

    def test_every_fact_has_evidence(self):
        payload = {"organisasjonsnummer": "923609016", "navn": "EQUINOR ASA", "konkurs": False}
        facts = facts_from_entity(payload, "https://example.test", "2026-10-12T00:00:00Z")
        self.assertTrue(facts)
        self.assertTrue(all(f.evidence.source_url and f.evidence.retrieved_at and f.evidence.json_path for f in facts))


if __name__ == "__main__":
    unittest.main()

