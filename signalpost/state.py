import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  organisation_number TEXT NOT NULL,
  source_url TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  PRIMARY KEY (organisation_number, source_url, content_sha256)
);
CREATE TABLE IF NOT EXISTS claims (
  organisation_number TEXT NOT NULL,
  claim_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  evidence_id TEXT,
  observed_at TEXT NOT NULL,
  PRIMARY KEY (organisation_number, claim_key)
);
CREATE TABLE IF NOT EXISTS claim_history (
  organisation_number TEXT NOT NULL,
  claim_key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  evidence_id TEXT,
  observed_at TEXT NOT NULL,
  UNIQUE (organisation_number, claim_key, value_json, evidence_id)
);
CREATE TABLE IF NOT EXISTS entities (
  organisation_number TEXT PRIMARY KEY,
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript(SCHEMA)

    def apply(self, orgnr: str, claims: list[dict[str, Any]], evidence: list[dict[str, Any]], observed_at: str) -> list[dict[str, Any]]:
        changes = []
        seen_before = self.connection.execute("SELECT 1 FROM entities WHERE organisation_number=?", (orgnr,)).fetchone() is not None
        previous_rows = self.connection.execute(
            "SELECT claim_key, value_json, evidence_id, observed_at FROM claims WHERE organisation_number=?",
            (orgnr,),
        ).fetchall()
        previous_by_key = {row[0]: row[1:] for row in previous_rows}
        for item in evidence:
            self.connection.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?)",
                (orgnr, item["source_url"], item["content_sha256"], item["retrieved_at"]),
            )
        for claim in claims:
            if claim.get("availability") != "available":
                continue
            key = claim["key"]
            value_json = json.dumps(claim.get("value"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            previous = previous_by_key.get(key)
            evidence_id = (claim.get("evidence_ids") or [None])[0]
            if previous and previous[0] != value_json:
                changes.append({
                    "claim_key": key,
                    "change_type": "updated",
                    "previous_value": json.loads(previous[0]),
                    "current_value": claim.get("value"),
                    "previous_evidence_id": previous[1],
                    "current_evidence_id": evidence_id,
                    "previous_observed_at": previous[2],
                    "observed_at": observed_at,
                })
            elif seen_before and previous is None:
                changes.append({"claim_key": key, "change_type": "added", "previous_value": None, "current_value": claim.get("value"), "previous_evidence_id": None, "current_evidence_id": evidence_id, "previous_observed_at": None, "observed_at": observed_at})
            self.connection.execute(
                "INSERT INTO claims VALUES (?, ?, ?, ?, ?) ON CONFLICT(organisation_number, claim_key) DO UPDATE SET value_json=excluded.value_json,evidence_id=excluded.evidence_id,observed_at=excluded.observed_at",
                (orgnr, key, value_json, evidence_id, observed_at),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO claim_history VALUES (?, ?, ?, ?, ?)",
                (orgnr, key, value_json, evidence_id, observed_at),
            )
        current_keys = {claim["key"] for claim in claims if claim.get("availability") == "available"}
        if seen_before:
            for key, previous in previous_by_key.items():
                if key not in current_keys:
                    changes.append({"claim_key": key, "change_type": "removed", "previous_value": json.loads(previous[0]), "current_value": None, "previous_evidence_id": previous[1], "current_evidence_id": None, "previous_observed_at": previous[2], "observed_at": observed_at})
                    self.connection.execute("DELETE FROM claims WHERE organisation_number=? AND claim_key=?", (orgnr, key))
        self.connection.execute(
            "INSERT INTO entities VALUES (?, ?, ?) ON CONFLICT(organisation_number) DO UPDATE SET last_observed_at=excluded.last_observed_at",
            (orgnr, observed_at, observed_at),
        )
        self.connection.commit()
        return changes

    def close(self) -> None:
        self.connection.close()

