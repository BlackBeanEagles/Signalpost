# SignalPost submission

## Deliverables ready

- Contract-compatible batch runner accepting Builderr-supplied companies
- Exactly one terminal envelope per input, including failures
- Allowed availability states and explicit missing fields
- Official identity, financials, roles, groups, workplaces and public-support awards
- Strictly verified company-owned descriptions, contact channels, careers/jobs, social links and activity pages
- Evidence hashes, timestamps, source classes and extraction methods
- Persistent snapshots, claim history and typed refresh changes
- Machine-readable 100-company report and audited output
- Pinned build dependency and zero runtime dependencies
- $0 third-party API cost

## Evaluator command

```bash
python -m signalpost run --organisations evaluator-companies.jsonl --bulk brreg-enheter.csv.gz --output out/envelopes.jsonl --report out/run-report.json --state state/signalpost.sqlite3 --run-id official-001 --workers 12
```

## Declared services and licences

- Brønnøysundregistrene Enhetsregisteret and Regnskapsregisteret public APIs
- Norwegian Licence for Open Government Data (NLOD) 2.0
- No model, paid API, personal credential, external cache or restricted-platform scraper
- Expected third-party cost per official run: $0
- Expected request count: one shared support snapshot plus budget-adaptive official/company-owned modules. The runner reduces enabled modules automatically to remain within the default 2,000-request limit as the evaluator batch grows.

## Smoke result

`reports/smoke-100-report.json` and `reports/smoke-100-envelopes.jsonl` contain a live 100-company repeat run. It completed all 100 inputs, produced no failed envelopes, used 439 requests, cost $0, and passed the local contract audit.

## External actions remaining

Repository URL: `ADD_AFTER_CREATING_THE_PUBLIC_REPOSITORY`

Exact commit hash: use `git rev-parse HEAD` after the final commit.

Contact details: `ADD_NAME_AND_EMAIL_BEFORE_SUBMISSION`

Send the repository URL, exact commit hash, evaluator command, API/licence declaration, expected cost and contact details to `submit@builderr.ai`. Register the project link on Unstop separately.

Builderr lists the challenge closing date as 21 October 2026 and says revised commit hashes close 18 October 2026. Unstop displayed an earlier 17 October registration deadline. Treat 17 October as the safe submission cutoff unless the organiser confirms otherwise.

