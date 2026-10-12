# Build plan

## Core data contract

```json
{
  "organization_number": "923609016",
  "legal_name": "Example AS",
  "retrieved_at": "2026-10-12T12:00:00Z",
  "facts": [
    {
      "field": "legal_name",
      "value": "Example AS",
      "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
      "source_published_or_updated_at": null,
      "retrieved_at": "2026-10-12T12:00:00Z",
      "evidence": "Canonical entity record returned for organization number 923609016",
      "confidence": 1.0
    }
  ],
  "warnings": []
}
```

Never emit an unsupported value. Unknown is better than guessed.

## Pipeline

`validate -> resolve canonical identity -> collect -> normalize -> verify identity -> resolve conflicts -> apply freshness rules -> emit`

### Identity gate

- Require the exact organisation number from a structured source.
- Treat the BRREG entity record as the canonical identity anchor.
- Do not join on company name alone.
- If another page lacks the organisation number, require a strong secondary match such as legal name plus official domain and address; otherwise keep the item out of the published profile.
- Record redirects, mergers, deletions, and HTTP 410 results explicitly.

### Evidence gate

- Every fact must retain its source URL, retrieval timestamp, and a compact evidence excerpt or structured JSON path.
- Store raw responses or content hashes for reproducibility.
- Keep source-specific parsers deterministic and testable.
- Financial values need period, currency, unit, scope, and source. If any are missing, do not publish the value.

### Freshness

- Re-fetch canonical BRREG data on every scored run unless a short TTL is permitted.
- Use field-level timestamps when the source supplies them.
- Compare a new profile with the prior snapshot and label added, changed, and removed facts.
- Never overwrite a newer fact with an older source.

## Practical architecture

- `src/signalpost/cli.py`: the one-command entry point
- `src/signalpost/sources/brreg.py`: official API client
- `src/signalpost/identity.py`: organisation-number validation and entity matching
- `src/signalpost/models.py`: profile/fact/evidence schema
- `src/signalpost/pipeline.py`: orchestration with request and cost budgets
- `src/signalpost/storage.py`: cached raw responses and versioned profiles
- `tests/`: identity, evidence, freshness, conflict, and budget tests
- `data/profiles.jsonl`: final 1,000+ profiles

An LLM should explain or summarize already verified facts. Deterministic code should handle identity matching, dates, financial normalization, evidence requirements, and publication decisions.

## Milestones

1. BRREG client, Modulus 11 validation, schemas, and CLI.
2. Generate and validate 1,000 BRREG-backed profiles.
3. Add snapshot comparison and freshness handling.
4. Add one or two permitted enrichment sources with strict identity adapters.
5. Add evaluation harness using a fixed set of organisation numbers and deliberate wrong-company/conflict cases.
6. Measure the 100-company run for time, request count, API cost, and failure rate.
7. Freeze the submission commit and document the exact command, models, APIs, and cost.

## Questions to confirm with the organiser

- Exact runner interface and expected JSON/output schema
- How the daily 100 organisation numbers are delivered
- Which public sources are explicitly permitted or prohibited
- Whether normal HTTP caching counts toward the 2,000-request limit
- How source dates are scored when a page only exposes a retrieval date
- Required contents of the emailed “code and required files” package
- Whether the Unstop deadline discrepancy (page timeline says 10:29 PM IST while its text says 11:59 PM IST) has been resolved

