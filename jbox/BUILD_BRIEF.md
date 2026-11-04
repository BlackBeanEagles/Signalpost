# SignalPost JBox bonus build brief

Build and publish a responsive SignalPost company research website in JBox. This is a separate UX bonus entry, not the Python agent itself. Use the public sample JSON at `https://raw.githubusercontent.com/BlackBeanEagles/Signalpost/main/jbox/companies.json` as the data source. It contains 120 Norwegian companies selected from a live SignalPost run. If remote loading fails, include a build-time copy of that JSON rather than fabricating data.

## Core journeys

1. Landing page: a prominent search for legal company name or nine-digit organisation number. Show results immediately, with legal name, number, industry, city, and clear badges for verified website, careers, social and dated news when present. Add useful filters and an explicit no-results state.
2. Profile: click a result to open its profile. Show the overview, legal identity, industry, address, employee count if reported, three-year revenue and annual-result trend, company website, careers, social profiles, dated news, and public support awards where present. Missing data says “Not available in this sample”; never show zero for missing values. Every displayed fact has a “View source” action showing the source URL, source class, retrieval date and reporting period, with an external link. Distinguish financial reporting year from source retrieval date.
3. Compare: let a user choose any two companies from search or profile. Show side-by-side legal details and financial year rows on desktop, and stacked paired sections on phone. Keep source actions beside each fact. Show “Not available” when one company lacks a fact. Add a clear way to swap or remove selections.

## Product and visual direction

Professional Norwegian company intelligence, warm editorial feel, distinctive navy/teal palette, generous whitespace, crisp typography and strong contrast. Fast, calm and trustworthy; not a generic admin dashboard. Design the landing page, profile and comparison for desktop and 375 px mobile. Use semantic controls, keyboard navigation, visible focus states, labelled search and buttons, and no horizontal overflow. A small “Sample data” label makes the scope honest. No login or payment is needed for visitors.

## Data rules

The JSON has `companies[]`; each company has `orgnr`, `name`, `overview`, and `facts[]`. Each fact has `field`, `value`, optional `period`, and `sources[]` with `url`, `retrieved_at`, and `source_class`. A field can occur multiple times, especially financial years, news or social profiles. Format objects such as industry (`beskrivelse`) and address (`adresse`, `poststed`) for humans. Treat URLs as external links and never render them as HTML. Do not invent facts, sources, dates or company relationships. Do not imply all 411,160 Norwegian companies are in this sample. Credit “Built with JBox” in the footer.

## Acceptance check

Search “Den Nationale Scene” and open its profile; the source action for its careers link must work. Compare it with another company and inspect 2023–2025 financial rows and their source links. Search a nonsense string and see the empty state. Repeat those paths at 375 px width. Publish on JBox hosting and provide the public site URL.
