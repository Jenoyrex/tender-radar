# What I built and learned: tender-radar

tender-radar is a free daily shortlist of open EU public tenders for small IT
companies. You describe your business, or give your company name, and every
morning you get a web page and an RSS feed with the 30 open tenders that fit you
best, each with the reasons it matched. Sign-up is a GitHub issue form; a GitHub
Action writes your profile, rebuilds the site and replies with your links. There is
no server and no paid API: everything runs on GitHub Actions and GitHub Pages.

## The data source

All data comes from TED, the EU's official procurement journal, through its
Search API v3. It is free and needs no key, which is the only reason a zero-cost
version of this exists. It has quirks: pages hold at most 250 notices, a query can
only page through 15,000 results, and answers occasionally arrive cut off mid-transfer,
which crashed my two-year backfill until the client learned to retry that error too.
I fetch one day at a time, cache every raw response, and fail loudly when a field
changes shape, because a silently wrong date or value is worse than a missing day.

Coverage is the first honest limitation: TED only carries contracts above the EU
thresholds (roughly €140k–€220k for services). Most small local contracts live on
national portals that tender-radar does not read.

## The language problem

A notice has an "English title", but it is a template: *country – CPV label –
original title*. Only the CPV label is in English. In 5,414 notices, 7.6% had a
genuine English title and about 5% an English description. Everything else is in
Czech, German, Spanish, Polish and twenty other languages. A matcher that only
understands English is blind to most of the text, and the English title quietly
leaks the CPV code, so the evaluations hide it from the matcher.

## Why simple TF-IDF won

I expected multilingual sentence embeddings to win. They did not. In three
evaluations with three kinds of ground truth, TF-IDF on character 3-to-5-grams was
never clearly beaten. Character n-grams match "software", "Software" and "softwaru"
without knowing any language, and they have no 470 MB model to download every
morning. In the final backtest, multilingual-e5-small on its own was the weakest
text matcher (top-10 hit rate 44% against 52% for the shipped one). A blend of the
two scored 2 points higher, but the 95% confidence interval of that gain ran from
−0.3 to +4.3 points. I had decided beforehand to ship a challenger only if it
clearly won on held-out data, so the simpler model stayed.

## Why the AI labels were unreliable

My second evaluation used 150 hand-labelled (profile, tender) pairs. "Hand" is
generous: I labelled 6 and asked an AI to label the other 144. On the 6 pairs we
both labelled, we agreed on 2, and the AI had seen my answers first. Relevance
("would this business bid on this?") is subjective and positives were rare (17 of
150). The numbers measured one labeller's taste. I kept them in the evaluation, clearly
marked, and stopped treating them as ground truth.

## The award-notice backtest

The better ground truth was in TED all along: contract award notices say who won
what. The question becomes concrete: if a company had used tender-radar, would the
tender it went on to win have been near the top of its list?

I fetched two years of IT award notices (45,190) and two and a half years of
contract notices, linked 65% of awards back to their call for tender through the
eForms procedure identifier, and grouped winners into companies. That was the
hardest part. National IDs looked like the obvious key, but 1,697 of 16,048 IDs
appeared with more than one company name, often a consortium partner's or another
bidder's ID. Lithuanian firms all start with "UAB", Swiss notices prefix names with
language tags, and three-letter names like "OCI" belong to unrelated firms. The final
rules are simple enough to explain in three lines, and in a hand-checked random
sample of 20 companies, 19 were clearly one firm and one was a corporate group.

For each of 1,427 companies with enough history, I built a profile from its earlier
wins only, collected every tender open in its countries on the day its next win
was published, and recorded where that tender ranked. On the held-out half: top 10
for 52% of companies, top 50 for 78%, against 14% for random order and 22% for
ranking by CPV code alone.

That is useful, and it is not as good as it sounds. The lists were short (about
140 open tenders) because the countries came from the company's own history.
Companies with many wins skew large. Follow-up contracts from the same buyer are
easy to find by text similarity. And it says nothing about a first-time bidder who
types three sentences, which is exactly who the product is for.

## What I would do next

Collect real feedback: the relevant / not-relevant links on every result now flow
into a CSV each day, but nobody has clicked one yet. Measure how often the top 10
contains a tender from a buyer the company has never worked with. Run the backtest
from typed descriptions instead of past wins. And read national portals, because
that is where most small contracts are.
