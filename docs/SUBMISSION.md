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
python -m signalpost run --organisations evaluator-companies.jsonl --output out/envelopes.jsonl --report out/run-report.json --state state/signalpost.sqlite3 --run-id official-001 --workers 24
```

## Declared services and licences

- Brønnøysundregistrene Enhetsregisteret and Regnskapsregisteret public APIs
- Norwegian Licence for Open Government Data (NLOD) 2.0
- No model, paid API, personal credential, external cache or restricted-platform scraper
- Expected third-party cost per official run: $0
- Install step from a clean checkout: `python -m pip install .`. No personal credentials or runtime packages are required.
- Expected request count: one bounded shared support-snapshot request, with one budgeted retry only for an initial connection failure, run concurrently with budget-adaptive official/company-owned modules. The default 17,000-request ceiling leaves headroom for the current 1,000-company batch and can be lowered to match an evaluator-supplied ceiling. Use optional `--bulk PATH` only when Builderr supplies that snapshot.

## Smoke result

`reports/smoke-300-v23-report.json` and `reports/smoke-300-v23-envelopes.jsonl` contain the post-feedback live 300-company run. It completed all 300 inputs, produced no failed envelopes, emitted 8,377 supported claims including 12 verified company sites, two dated news items, three exact-account social profiles and 11 recent official support awards, used 1,773 requests, cost $0, completed in 337.3 seconds, and passed the local contract audit. The support snapshot is explicitly partial after its 60-second deadline; unobserved awards remain unknown. These are local smoke metrics from a different sample, not Builderr's official score.

## External actions remaining

Repository URL: `https://github.com/BlackBeanEagles/Signalpost`

Exact commit hash: use `git rev-parse HEAD` after the final commit.

Contact details: use the registration email and participant name from the Unstop entry.

Send the repository URL, exact commit hash, evaluator command, API/licence declaration, expected cost and contact details to `submit@builderr.ai`. Register the project link on Unstop separately.

The organiser's 2 November feedback reports 274 of 300 companies reached on a previous run, with nine checked facts right and none wrong; the final score remains pending. Send the latest exact commit URL when updating the submission. Builderr allows five submitted versions in total through 7 November; repository commits alone do not establish which version is recorded for the next run.

