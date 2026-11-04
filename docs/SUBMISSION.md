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

`reports/smoke-300-v25-report.json` and `reports/smoke-300-v25-envelopes.jsonl` contain the post-feedback live 300-company run. It completed all 300 inputs, produced no failed envelopes, emitted 8,406 supported claims including 16 verified company sites, three dated news items, seven exact-account social profiles, two company careers pages and 11 recent official support awards, used 1,838 requests, cost $0, completed in 175.7 seconds, and passed the local contract audit. The support snapshot is explicitly partial after its 60-second deadline; unobserved awards remain unknown. These are local smoke metrics from a different sample, not Builderr's official score.

`reports/coverage-1000-v27-report.json` and its envelopes contain a larger local run against `data/smoke-organisations-1000.jsonl`: 1,000/1,000 outputs, zero failed envelopes, 54 verified websites, 14 exact social profiles, five genuine careers pages and two dated company news items. It used 5,904 requests, cost $0 in external API fees, took 804.2 seconds, and passed the contract audit. The earlier local run on that same input had 38 websites, five social profiles and one careers page. Live reachability can vary; this is still not an official Builderr score.

## External actions remaining

Repository URL: `https://github.com/BlackBeanEagles/Signalpost`

Exact commit hash: use `git rev-parse HEAD` after the final commit.

Contact details: use the registration email and participant name from the Unstop entry.

Send the repository URL, exact commit hash, evaluator command, API/licence declaration, expected cost and contact details to `submit@builderr.ai`. Register the project link on Unstop separately.

The organiser's 2 November feedback reports 274 of 300 companies reached on a previous run, with nine checked facts right and none wrong; the final score remains pending. Send the latest exact commit URL when updating the submission. Builderr allows five submitted versions in total through 7 November; repository commits alone do not establish which version is recorded for the next run.

