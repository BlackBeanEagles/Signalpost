# SignalPost

An evidence-first agent for Norwegian company research.

## What the hackathon asks for

Input: a Norwegian nine-digit organisation number (`organisasjonsnummer`).

Output: useful, current company facts where every published fact includes:

- the exact organisation number it belongs to;
- a source URL;
- the source or retrieval date;
- a short explanation;
- enough evidence to verify the claim.

The submission must include at least 1,000 company profiles, a repository URL, an exact commit hash, one command to run the agent, model/API details, and expected run costs.

## Scoring and hard limits

- Coverage: 35 points (minimum 21/35)
- Correct company matching and evidence: 30 points
- Correct updates/freshness: 20 points
- Useful explanations: 10 points
- Ease of use: 5 points
- Qualification: at least 65/100 overall plus all published accuracy, evidence, and execution requirements
- Daily evaluation: 100 random companies, 45 minutes, 2,000 outbound requests, and $10 declared external API cost
- A material wrong-company publication or fabricated financial value fails the entry

## Implemented solution

1. Validates every organisation number using the Norwegian Modulus 11 rule.
2. Fetches canonical records from Brønnøysundregistrene (BRREG).
3. Locks every profile to the returned organisation number and legal name.
4. Normalizes rich company facts into a consistent evidence-bearing schema.
5. Rejects wrong-company responses and facts without values.
6. Generates deterministic JSON or readable summaries.
7. Produces and validates a 1,000-profile JSONL submission dataset.
8. Enforces the published 2,000-request and $10 API-cost budgets.

Start with BRREG only. It is the official source and can provide legal name, organisation form, addresses, industry codes, registration dates, status/register memberships, website/contact fields when present, and roles through the public roles endpoint. Add other sources only after source terms and identity matching are explicit.

Official BRREG API documentation: https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html

Hackathon page: https://unstop.com/hackathons/signalpost-build-an-agent-that-finds-company-information-builderrai-1754883

## Run

Requires Python 3.10+ and no third-party packages.

```powershell
# One company
python -m signalpost profile 923609016 --format json

# Generate the required dataset
python -m signalpost batch --count 1000 --output data/profiles.jsonl

# Audit identity, uniqueness and evidence completeness
python -m signalpost validate data/profiles.jsonl --minimum 1000

# Run tests
python -m unittest discover -s tests -v
```

On Windows, `./run.ps1 profile 923609016`, `./run.ps1 batch`, and `./run.ps1 validate` provide the same workflow.

## Models, APIs and expected cost

- Model: none required. This removes hallucination risk from identity matching and fact publication.
- API: official BRREG Enhetsregisteret Open Data REST API.
- Authentication: none for the endpoints used.
- External API cost: $0.
- A 100-company live run needs 100 requests. The included 1,000-profile dataset was produced from paginated official results in 10 requests.
- Optional future language-model summaries must operate only on already verified facts and must never change values or publication decisions.

## Included submission data

- `data/profiles.jsonl`: 1,000 unique evidence-bearing profiles.
- `data/profiles.jsonl.manifest.json`: count, SHA-256 checksum, source and budget use.

See `docs/SUBMISSION.md` for the final checklist and known organiser-dependent items.


