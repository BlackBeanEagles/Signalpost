# SignalPost submission

## Deliverables ready

- Contract-compatible batch runner accepting Builderr-supplied companies
- Exactly one terminal envelope per input, including failures
- Allowed availability states and explicit missing fields
- Official identity, financials, roles, groups, workplaces and public-support awards
- Company-owned descriptions, contact channels, careers/jobs, social links and dated news only when exact-entity evidence supports them
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
- Expected request count: one shared support snapshot plus budget-adaptive official/company-owned modules. The default 17,000-request ceiling is sized to retain the high-value role, location, group and verified-website modules plus up to two bounded exact-identity website discovery candidates on the current 1,500-company official batch; `--max-requests` can be lowered to match an evaluator-supplied ceiling.

## Smoke result

`reports/smoke-100-v13-report.json` and `reports/smoke-100-v13-envelopes.jsonl` contain the post-audit live 100-company run. It completed all 100 inputs, produced no failed envelopes, emitted 3,468 supported claims including four verified company sites, two dated news items and two exact-account social profiles, used 576 requests, cost $0, and passed the local contract audit. The shared support-awards download timed out, so those claims were unavailable in this sample. These are local smoke metrics, not Builderr's pending fresh-company score.

## External actions remaining

Repository URL: `https://github.com/BlackBeanEagles/Signalpost`

Exact commit hash: use `git rev-parse HEAD` after the final commit.

Contact details: use the registration email and participant name from the Unstop entry.

Send the repository URL, exact commit hash, evaluator command, API/licence declaration, expected cost and contact details to `submit@builderr.ai`. Register the project link on Unstop separately.

The organiser's latest direct email confirms the recorded submission at commit `5445c95` (version 2 of 5) and asks for audit fixes before 7 November. Send the new exact commit URL when the updated revision is ready; the published score is still pending its fresh-company rerun.

