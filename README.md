# SignalPost

Competition-ready, evidence-first research for Norwegian companies. The evaluator supplies a JSON, JSONL or text batch of organisation numbers; SignalPost returns exactly one terminal JSONL envelope per input.

## Evaluator command

Python 3.10+ is the only runtime requirement. There are no runtime packages or personal credentials.

```bash
python -m signalpost run --organisations evaluator-companies.jsonl --bulk brreg-enheter.csv.gz --output out/envelopes.jsonl --report out/run-report.json --state state/signalpost.sqlite3 --run-id official-001 --workers 12
```

Audit the result:

```bash
python -m signalpost audit --organisations evaluator-companies.jsonl --output out/envelopes.jsonl
```

Build the responsive verification interface:

```bash
python -m signalpost product --envelopes out/envelopes.jsonl --output out/signalpost.html
```

## Coverage

For every valid organisation number the agent queries five official Norwegian sources:

- Enhetsregisteret identity and company details;
- Regnskapsregisteret financial statements;
- official registered roles;
- official corporate-group structure;
- official registered workplaces/subunits.
- the shared official Støtteregisteret award snapshot when it completes within its bounded transfer deadline.

The frozen bulk registry snapshot is used for identity without consuming outbound requests. The runner automatically chooses the highest-value additional modules that fit the batch size and `--max-requests` budget, so a growing official batch still returns every required envelope.

Claims include legal identity, industry, addresses, employees, contact details, business purpose, filing status, financial results across reporting periods, management and board roles, group relationships, and workplaces. Missing, blocked and failed modules are explicit; missing values are never changed to zero.

## Accuracy and evidence

- Norwegian Modulus 11 validation before any request
- Exact returned organisation-number match before publication
- Fixed HTTPS allowlist: `data.brreg.no`
- Immutable SHA-256 source snapshots
- Retrieval time, extraction method and source class for every evidence record
- Every available claim resolves to evidence
- Bounded responses, timeouts, request budget and external cost budget
- No LLM-generated or inferred facts

## Refresh

SQLite state stores immutable source snapshots, claim history and current values. Replaying the same data creates no false changes. Added, updated and removed claims carry earlier and current evidence references.

## Smoke-test result

The checked-in report and envelopes under `reports/` are a live 100-company run:

- 100 inputs and 100 terminal outputs
- 0 failed companies
- 3,669 supported claims, including 223 strictly verified company-site claims across 13 companies
- 538 evidence records from 625 requests
- 0 false changes on an immediate repeat
- $0 third-party API cost
- 94.6 seconds wall time
- Responsive search and source-verification interface in `reports/signalpost.html`

Run the tests with:

```bash
python -m unittest discover -s tests -v
```

The current suite contains 20 deterministic tests.

## Source rights and operations

Only official Brønnøysundregistrene open-data endpoints are enabled. The data is published under the Norwegian Licence for Open Government Data (NLOD) 2.0. No restricted social, job or search platform is scraped. Runtime dependencies are empty; the build backend is pinned.

The official challenge contract scores 50 recall/coverage, 30 precision/evidence, 12 synthesis and 8 UX. SignalPost prioritizes exact-company official coverage and reproducibility. See `docs/SUBMISSION.md` for the final external submission steps.

