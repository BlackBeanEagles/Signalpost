# Submission checklist

## Ready

- Working Python 3.10+ agent with no third-party dependencies
- Exact organisation-number validation and wrong-company rejection
- Official-source facts with URLs, timestamps, JSON paths, confidence and explanations
- Deterministic JSON and readable output
- 1,000 unique company profiles in `data/profiles.jsonl`
- Dataset manifest with SHA-256 digest and request/cost accounting
- Validator and automated unit tests
- One-command Windows runner
- API/model/cost documentation

## Before emailing Builderr

1. Confirm the runner input/output contract and adapt `signalpost/cli.py` if they require a particular envelope.
2. Confirm permitted sources and whether BRREG-only coverage is competitive enough.
3. Create a public repository and push the frozen commit.
4. Put the repository URL and exact commit hash below.
5. Register and share the project link on Unstop.
6. Email the complete entry to `submit@builderr.ai` before the confirmed deadline.

Repository URL: `TO_BE_ADDED_AFTER_REMOTE_REPOSITORY_CREATION`

Exact commit hash: `TO_BE_ADDED_AFTER_FINAL_COMMIT`

Run command: `python -m signalpost profile <NORWEGIAN_ORGANISATION_NUMBER> --format json`

Batch command: `python -m signalpost batch --count 1000 --output data/profiles.jsonl`

Model/API: no model; BRREG Enhetsregisteret Open Data REST API; $0 expected external API cost.

## Deadline warning

The Unstop page displayed 17 October 2026 at 10:29 PM IST in its structured timeline, while descriptive text said 11:59 PM IST. Confirm the actual cutoff with the organiser and use the earlier time until clarified.

