"""Generate the static site: one HTML page + RSS feed per profile, and an index
with a filterable table of open tenders."""

import datetime as dt
import json
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape as xesc

from . import match, util

SITE_URL = "https://jenoyrex.github.io/tender-radar"
ATTRIBUTION = (
    'Source: <a href="https://ted.europa.eu">TED – Tenders Electronic Daily</a>, '
    "© European Union, Publications Office of the EU. Reused under Commission Decision 2011/833/EU. "
    "tender-radar is unofficial and not affiliated with the EU. Always check the official notice."
)
TOP_N = 30

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;--accent:#1f5f8b;--chip:#eef3f7}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#9c9a92;--line:#2c2b28;--accent:#7fb6dd;--chip:#1f2a33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 48px}a{color:var(--accent)}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.15rem;margin:2em 0 .5em}.muted{color:var(--muted)}
.card{border-top:1px solid var(--line);padding:14px 0}.card h3{font-size:1rem;margin:0 0 4px;line-height:1.35}
.meta{font-size:.875rem;color:var(--muted)}.meta b{color:var(--fg);font-weight:600}
.chips{margin:6px 0 0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:4px}
.chips li{background:var(--chip);border-radius:4px;padding:1px 7px;font-size:.8rem}
.fb{font-size:.8rem;color:var(--muted);margin-top:6px}.fb a{color:var(--muted)}
.score{float:right;font-variant-numeric:tabular-nums;font-weight:600;margin-left:8px}
.lead{font-size:1.15rem}.steps{padding-left:1.3em}.steps li{margin:.4em 0}
.btn{display:inline-block;background:var(--accent);color:var(--bg);padding:9px 16px;border-radius:6px;text-decoration:none;font-weight:600}
footer{margin-top:40px;padding-top:12px;border-top:1px solid var(--line);font-size:.8rem;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.filters label{display:flex;flex-direction:column;font-size:.75rem;color:var(--muted);gap:2px}
input,select{font:inherit;font-size:.9rem;padding:5px 7px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg);min-width:0}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.875rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{position:sticky;top:0;background:var(--bg);cursor:pointer;white-space:nowrap}td.num{text-align:right;white-space:nowrap}
"""


def page(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>{CSS}</style>{extra_head}</head><body><main>{body}<footer>{ATTRIBUTION}
Generated {dt.date.today().isoformat()} by <a href="https://github.com/Jenoyrex/tender-radar">tender-radar</a>.</footer></main></body></html>"""


def money(t) -> str:
    if t["value"] is None:
        return "not published"
    s = f"{t['value']:,.0f} {t['currency']}"
    return s if t["currency"] == "EUR" or t["value_eur"] is None else f"{s} (≈ €{t['value_eur']:,.0f})"


REPO = "https://github.com/Jenoyrex/tender-radar"


def feedback_url(t, slug: str, verdict: str) -> str:
    """Prefilled GitHub issue. The first body line is machine-readable for later use as labels."""
    body = (
        f"feedback: {verdict} | profile: {slug} | tender: {t['id']} | score: {t['score']:.3f}\n\n"
        f"Tender: {t['title_en'] or t['title']}\n{t['link']}\n\n"
        "Optional: why? (Please don't include personal data; issues are public.)\n"
    )
    q = urlencode({"title": f"[feedback] {verdict}: {slug} / {t['id']}", "body": body, "labels": "feedback"})
    return f"{REPO}/issues/new?{q}"


def card(t, slug: str = "") -> str:
    chips = "".join(f"<li>{escape(r)}</li>" for r in t["reasons"])
    fb = (
        (
            f'<div class="fb">Useful match? <a href="{escape(feedback_url(t, slug, "relevant"))}" rel="nofollow">👍 relevant</a>'
            f' · <a href="{escape(feedback_url(t, slug, "not relevant"))}" rel="nofollow">👎 not relevant</a></div>'
        )
        if slug
        else ""
    )
    return f"""<div class="card"><span class="score" title="match score">{t["score"]:.2f}</span>
<h3><a href="{t["link"]}">{escape(t["title_en"] or t["title"])}</a></h3>
<div class="meta"><b>{escape(t["buyer"] or "?")}</b> · {t["country"]} · value {money(t)} ·
deadline <b>{t["deadline"] or "see notice"}</b> · published {t["published"]}</div><ul class="chips">{chips}</ul>{fb}</div>"""


def rss(p: match.Profile, results: list[dict]) -> str:
    now = format_datetime(dt.datetime.now(dt.UTC))
    items = "".join(
        f"""<item><title>{xesc(t["title_en"] or t["title"])}</title><link>{t["link"]}</link>
<guid isPermaLink="false">ted-{t["id"]}</guid><pubDate>{format_datetime(dt.datetime.fromisoformat(t["published"]).replace(tzinfo=dt.UTC))}</pubDate>
<description>{xesc(f"Score {t['score']:.2f}. Buyer: {t['buyer']} ({t['country']}). Value: {money(t)}. Deadline: {t['deadline'] or 'see notice'}. Why: {'; '.join(t['reasons'])}. Source: TED, © European Union.")}</description></item>"""
        for t in results
    )
    return f"""<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<title>{xesc(p.name)} – tender-radar</title><link>{SITE_URL}/p/{p.slug}.html</link>
<description>Open EU tenders matching this profile. Data: TED, © European Union. Unofficial.</description>
<lastBuildDate>{now}</lastBuildDate>{items}</channel></rss>"""


def profile_page(p: match.Profile, results: list[dict]) -> str:
    filt = []
    if p.countries:
        filt.append("countries " + ", ".join(p.countries))
    if p.min_value_eur or p.max_value_eur:
        filt.append(
            f"value €{p.min_value_eur or 0:,.0f}–{('€' + format(p.max_value_eur, ',.0f')) if p.max_value_eur else 'any'} (unpublished values kept)"
        )
    if p.exclude_keywords:
        filt.append("excluding " + ", ".join(p.exclude_keywords))
    body = f"""<p><a href="../index.html">← all profiles</a></p><h1>{escape(p.name)}</h1>
<p>{escape(p.description)}</p><p class="meta">Filters: {escape("; ".join(filt) or "none")}. Preferred CPV: {", ".join(p.cpv) or "none"}.
<a href="{p.slug}.xml">RSS feed</a></p>
<p class="meta">The 👍/👎 links open a public GitHub issue (needs a free GitHub account). Feedback becomes labels for the next evaluation round.</p>
<h2>Top {len(results)} open tenders</h2>{"".join(card(t, p.slug) for t in results) or "<p>No open tenders match right now.</p>"}"""
    return page(f"{p.name} – tender-radar", body, f'<link rel="alternate" type="application/rss+xml" href="{p.slug}.xml">')


INDEX_JS = """
const $=s=>document.querySelector(s);let rows=[],sortKey='published',dir=-1;
fetch('tenders.json').then(r=>r.json()).then(d=>{rows=d;
 [...new Set(d.map(r=>r.country))].sort().forEach(c=>$('#f-country').add(new Option(c,c)));render();});
function render(){const c=$('#f-country').value,cpv=$('#f-cpv').value.trim(),q=$('#f-q').value.toLowerCase(),
 lo=+$('#f-min').value||0,hi=+$('#f-max').value||Infinity,dl=$('#f-dl').value,known=$('#f-known').checked;
 const f=rows.filter(r=>(!c||r.country===c)&&(!cpv||r.cpv.split(' ').some(x=>x.startsWith(cpv)))
  &&(!q||(r.title_en+' '+r.buyer).toLowerCase().includes(q))
  &&(r.value_eur==null?!known:r.value_eur>=lo&&r.value_eur<=hi)&&(!dl||(r.deadline&&r.deadline>=dl)));
 f.sort((a,b)=>((a[sortKey]??'')>(b[sortKey]??'')?1:(a[sortKey]??'')<(b[sortKey]??'')?-1:0)*dir);
 $('#count').textContent=f.length+' of '+rows.length+' open tenders';
 $('#tb').innerHTML=f.slice(0,300).map(r=>`<tr><td><a href="${r.link}">${esc(r.title_en)}</a><div class=meta>${esc(r.buyer||'')}</div></td>
 <td>${r.country}</td><td class=num>${r.value_eur==null?'–':'€'+Math.round(r.value_eur).toLocaleString('en')}</td>
 <td class=num>${r.deadline||'–'}</td><td class=num>${r.published}</td></tr>`).join('');}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
document.querySelectorAll('.filters input,.filters select').forEach(e=>e.addEventListener('input',render));
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{dir=sortKey===th.dataset.k?-dir:1;sortKey=th.dataset.k;render();});
"""


def row(r) -> str:
    """Same markup as INDEX_JS render(), so the server-rendered rows match the JS ones."""
    v = "–" if r["value_eur"] is None else f"€{round(r['value_eur']):,}"
    return (
        f'<tr><td><a href="{escape(r["link"])}">{escape(r["title_en"] or "")}</a><div class=meta>{escape(r["buyer"] or "")}</div></td>'
        f"<td>{r['country']}</td><td class=num>{v}</td><td class=num>{r['deadline'] or '–'}</td><td class=num>{r['published']}</td></tr>"
    )


SIGNUP_URL = f"{REPO}/issues/new?template=signup.yml"


def headline_html(h: dict | None) -> str:
    """One honest sentence from data/backtest-summary.json (written by `tender-radar backtest`)."""
    if not h:
        return "<p>How well the ranking works is being measured; see the evaluation.</p>"
    cpv = f", ranking by CPV code alone: {100 * h['hit10_cpv']:.0f}%" if "hit10_cpv" in h else ""
    return (
        f"<p>We replayed two years of EU IT contracts for <b>{h['companies']}</b> companies: for each, we built a profile "
        f"from its earlier wins and ranked the tenders open in its countries when its next win was published (typically about 140). That tender was "
        f"in the top 10 for <b>{100 * h['hit10']:.0f}%</b> of companies (random order: {100 * h['hit10_random']:.0f}%{cpv}) "
        f"and in the top 50 for {100 * h['hit50']:.0f}%. We also tested multilingual AI embeddings; they did not clearly "
        "do better, so the simpler text matcher stays. Useful as a shortlist, not a guarantee.</p>"
    )


def index_page(summaries, rows=(), headline: dict | None = None) -> str:
    examples = [(p, n) for p, n in summaries if not p.signup_issue]
    n_self = len(summaries) - len(examples)
    profs = "".join(
        f"""<div class="card"><h3><a href="p/{p.slug}.html">{escape(p.name)}</a></h3>
<div class="meta">{n} open tenders pass the filters · <a href="p/{p.slug}.xml">RSS</a></div><p class="meta">{escape(p.description)}</p></div>"""
        for p, n in examples
    )
    body = f"""<h1>tender-radar</h1>
<p class="lead">A free daily shortlist of open EU public tenders for IT and software services, ranked for your business,
as a web page and an RSS feed.</p>
<p><b>For</b> small IT companies (web studios, data and BI consultancies, managed IT and support providers, software houses)
that want to bid on public contracts across Europe without reading thousands of notices.</p>
<h2>How it works</h2>
<ol class="steps">
<li>You describe your business in a few sentences, or give your company name and we use its past EU contract wins.</li>
<li>Every morning we fetch new calls for tender from <a href="https://ted.europa.eu">TED</a>, the EU's official procurement journal
(IT services, CPV 72), drop closed ones and those outside your countries or value range, and rank the rest by how
similar their text is to your description.</li>
<li>Your page and RSS feed list the best 30, each with the reasons it matched. Always read the official notice before bidding.</li>
</ol>
<p><a class="btn" href="{SIGNUP_URL}">Get my tender feed</a></p>
<p class="meta">Sign-up is a short form on GitHub (needs a free GitHub account). Everything you type is public, so don't include
personal data. A bot replies with your links within minutes. You can remove your feed the same way.</p>
<h2>How good is the ranking?</h2>{headline_html(headline)}
<p class="meta"><a href="{REPO}/blob/main/docs/evaluation.md">Full evaluation and limitations</a>. Coverage: only tenders above the EU
thresholds are published on TED; most small, local contracts are only on national portals.</p>
<h2>Example profiles</h2>{profs}
{f'<p class="meta">Plus {n_self} self-serve feed{"s" if n_self != 1 else ""}.</p>' if n_self else ""}
<h2>Browse open tenders</h2><p class="meta" id="count">{min(len(rows), 50)} newest of {len(rows)} open tenders (filters need JavaScript)</p>
<div class="filters">
<label>Search<input id="f-q" type="search" placeholder="title or buyer"></label>
<label>Country<select id="f-country"><option value="">All</option></select></label>
<label>CPV starts with<input id="f-cpv" inputmode="numeric" size="8" placeholder="e.g. 7226"></label>
<label>Min € <input id="f-min" type="number" min="0" step="10000" style="width:8em"></label>
<label>Max € <input id="f-max" type="number" min="0" step="10000" style="width:8em"></label>
<label>Deadline on/after<input id="f-dl" type="date"></label>
<label>Value known only<input id="f-known" type="checkbox"></label></div>
<div class="tablewrap"><table><thead><tr><th data-k="title_en">Tender</th><th data-k="country">Country</th>
<th data-k="value_eur">Value</th><th data-k="deadline">Deadline</th><th data-k="published">Published ▾</th></tr></thead>
<tbody id="tb">{"".join(row(r) for r in rows[:50])}</tbody></table></div><p class="meta">Showing at most 300 rows; narrow with the filters.</p>
<script>{INDEX_JS}</script>"""
    return page("tender-radar – EU tenders for small businesses", body)


def latest_versions(tenders: list[dict]) -> list[dict]:
    """Buyers often re-publish the same call (corrections) under a new notice id.
    Keep only the newest notice per (buyer, title)."""
    best = {}
    for t in tenders:
        k = ((t["buyer"] or "").lower(), (t["title"] or "").lower())
        if k not in best or (t["published"], t["id"]) > (best[k]["published"], best[k]["id"]):
            best[k] = t
    return list(best.values())


def build(tenders: list[dict], profiles_dir: Path, out: Path, method: str = "tfidf", doc_vecs=None) -> list[dict]:
    today = dt.date.today()
    open_ = latest_versions([t for t in tenders if not t["deadline"] or t["deadline"] >= today.isoformat()])
    (out / "p").mkdir(parents=True, exist_ok=True)
    summaries = []
    for f in sorted(Path(profiles_dir).glob("*.yaml")):
        p = match.Profile.load(f)
        results = match.rank(open_, p, method=method, today=today, top=TOP_N, doc_vecs=doc_vecs)
        util.write_text(out / "p" / f"{p.slug}.html", profile_page(p, results))
        util.write_text(out / "p" / f"{p.slug}.xml", rss(p, results))
        n = sum(match.passes_filters(t, p, today) for t in open_)
        summaries.append((p, n))
    keep = ("id", "title_en", "buyer", "country", "cpv", "value_eur", "deadline", "published", "link")
    # Newest first, matching the JS default sort, so server-rendered rows are what JS shows too.
    rows = sorted(({k: t[k] for k in keep} for t in open_), key=lambda r: r["published"], reverse=True)
    util.write_text(out / "tenders.json", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    summary = Path(profiles_dir).parent / "data" / "backtest-summary.json"
    headline = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None
    util.write_text(out / "index.html", index_page(summaries, rows, headline))
    util.write_text(out / ".nojekyll", "")
    return open_
