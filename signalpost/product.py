import html
import json
from pathlib import Path
from urllib.parse import urlparse


def build_html(envelopes_path: Path, output_path: Path) -> None:
    rows = [json.loads(line) for line in envelopes_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cards = []
    for row in rows:
        org = html.escape(str(row.get("organisation_number", "")))
        synthesis = row.get("synthesis") or {}
        name = html.escape(str(synthesis.get("headline") or org))
        status = html.escape(str(row.get("availability") or "failed"))
        claim_rows = []
        evidence_by_id = {item.get("id"): item for item in row.get("evidence", []) if isinstance(item, dict)}
        for claim in row.get("claims", []):
            if claim.get("availability") != "available":
                continue
            value = json.dumps(claim.get("value"), ensure_ascii=False)
            if len(value) > 500:
                value = value[:497] + "…"
            links = []
            for evidence_id in claim.get("evidence_ids") or []:
                evidence = evidence_by_id.get(evidence_id, {})
                url = html.escape(str(evidence.get("source_url", "")), quote=True)
                retrieved = html.escape(str(evidence.get("retrieved_at", "")))
                parsed = urlparse(str(evidence.get("source_url", "")))
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    source_class = html.escape(str(evidence.get("source_class") or "source").replace("_", " "))
                    links.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{source_class} · {retrieved[:10]}</a>')
            claim_rows.append(f'<tr><th>{html.escape(str(claim.get("field")))}</th><td>{html.escape(value)}</td><td>{" ".join(links)}</td></tr>')
        changes = row.get("changes") or []
        change_html = "" if not changes else f'<p class="changes">{len(changes)} verified change(s) since the previous run</p>'
        cards.append(f'''<article class="card" data-search="{name.casefold()} {org}">
<header><div><h2>{name}</h2><p>{org}</p></div><span class="status {status}">{status}</span></header>
<p>{html.escape(str(synthesis.get("explanation") or ""))}</p>{change_html}
<details><summary>{len(claim_rows)} supported claims · view evidence</summary><div class="table-wrap"><table><tbody>{''.join(claim_rows)}</tbody></table></div></details>
</article>''')
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SignalPost company intelligence</title>
<style>:root{{--ink:#13231c;--muted:#617069;--paper:#f4f1e8;--card:#fff;--accent:#0b6b4f;--line:#d8ddd8}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}.hero{{background:#102d23;color:white;padding:3rem max(1rem,calc((100% - 1100px)/2)) 2.5rem}}h1{{font:700 clamp(2rem,6vw,4rem)/1 Georgia,serif;margin:0 0 .7rem}}.hero p{{max-width:65ch;color:#cfe3da}}main{{max-width:1100px;margin:auto;padding:1.5rem}}input{{width:100%;padding:1rem;border:1px solid var(--line);border-radius:12px;font:inherit;margin-bottom:1rem}}.grid{{display:grid;gap:1rem}}.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.2rem;box-shadow:0 3px 16px #1232}}header{{display:flex;justify-content:space-between;gap:1rem;align-items:start}}h2{{font:700 1.35rem Georgia,serif;margin:0}}header p{{margin:.2rem 0;color:var(--muted)}}.status{{padding:.25rem .6rem;border-radius:99px;background:#e4f3eb;color:var(--accent);font-size:.8rem}}summary{{cursor:pointer;color:var(--accent);font-weight:650}}.table-wrap{{overflow:auto;margin-top:1rem}}table{{width:100%;border-collapse:collapse;min-width:650px}}th,td{{text-align:left;vertical-align:top;border-top:1px solid var(--line);padding:.65rem}}th{{width:24%;font-size:.85rem}}td:nth-child(2){{word-break:break-word}}a{{color:var(--accent)}}.changes{{color:#8a4b08;font-weight:650}}@media(max-width:600px){{.hero{{padding-top:2rem}}main{{padding:.8rem}}.card{{padding:1rem}}}}</style></head>
<body><section class="hero"><h1>SignalPost</h1><p>Evidence-first Norwegian company intelligence. Every visible fact links back to an official source and retrieval date.</p></section><main><input id="q" type="search" placeholder="Search company name or organisation number" aria-label="Search companies"><p id="count">{len(cards)} companies</p><section class="grid" id="companies">{''.join(cards)}</section></main>
<script>const q=document.querySelector('#q'),cards=[...document.querySelectorAll('.card')],count=document.querySelector('#count');q.addEventListener('input',()=>{{let n=0,s=q.value.toLowerCase();for(const c of cards){{let show=c.dataset.search.includes(s);c.hidden=!show;if(show)n++}}count.textContent=n+' companies'}})</script></body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")

