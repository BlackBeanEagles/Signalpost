# Output schema

SignalPost emits one JSON object per input line.

- `organisation_number`: exact input entity identifier
- `availability`: `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous` or `failed`
- `run`: run ID and terminal timestamps
- `claims`: stable key, field, value, availability, confidence, evidence IDs and reporting period when relevant
- `evidence`: source URL/class, retrieval time, SHA-256 content hash, claim span and extraction method
- `source_snapshots`: immutable snapshot references used by refresh
- `changes`: added, updated or removed claim values with earlier/current evidence references
- `synthesis`: supported-fact count, changes, unknown families and a grounded explanation
- `errors`: module or company failures that were not silently dropped
- `operations`: request, runtime and third-party cost accounting

Every `available` claim must resolve to at least one evidence ID. The local `audit` command enforces count/order, states, evidence references, official HTTPS hosts, hashes and legal identity.

