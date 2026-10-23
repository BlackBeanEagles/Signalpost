# Source and publication policy

Official-record sources use Brønnøysundregistrene open-data endpoints on `https://data.brreg.no`:

- Enhetsregisteret entities, roles, group structure and subunits
- Regnskapsregisteret annual-account data
- Støtteregisteret public-support awards, using only the primary recipient organisation number. A bounded incomplete CSV snapshot is labeled partial, and missing rows are not treated as proof of no award.

The sources use the Norwegian Licence for Open Government Data (NLOD) 2.0. SignalPost sends no secrets or personal account credentials.

The organisation number is the identity anchor. A response is published only when the returned identifier exactly matches the requested identifier. Financial facts retain their reporting period and record identity. Missing values stay missing; zero is published only when the official response explicitly contains zero.

LinkedIn, Meta, Glassdoor, Indeed, Google and unofficial scraper clients are disabled. New connectors may be added only after documenting their licence/terms, enforcing a fixed outbound allowlist, preserving immutable evidence, and passing a zero-wrong-company evaluation gate.

Company-owned pages are fetched from the registry-listed website or a bounded discovery candidate. DNS and every redirect are rejected if they resolve to a private, loopback, link-local or otherwise non-public address. The homepage must identify the legal entity through its organisation number or matching branding on the registry-listed domain. A group homepage, a different legal name, or a page listing multiple legal entities is withheld. Discovery candidates without a registry-listed domain require the exact organisation number. When the registered homepage is a company subsection, crawling stays within that subsection.

Footer social links and navigation labels are never published as company profiles or news. Social links require exact-company Organization structured data and an exact account slug, excluding parent-group handles that merely contain the company name. Homepage redirects to another domain are withheld, and linked-page redirects outside the verified site or company subsection are ignored. News items require an individual same-site article, its own `datePublished`, and article content about the company. Job listings require exact-company `hiringOrganization` structured data. Ambiguous material remains unavailable rather than being attributed to the wrong company.

