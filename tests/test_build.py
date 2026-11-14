from tender_radar import build, match


def prof(slug, issue=None):
    return match.Profile(slug=slug, name=slug.title(), description="We build websites.", signup_issue=issue)


def test_index_explains_and_links_signup_and_lists_only_examples():
    html = build.index_page([(prof("example"), 3), (prof("someone-12", 12), 5), (prof("other-13", 13), 1)])
    assert "How it works" in html and build.SIGNUP_URL in html
    assert 'href="p/example.html"' in html and "someone-12" not in html
    assert "Plus 2 self-serve feeds." in html


def test_headline_is_honest_about_pending_and_baseline():
    assert "being measured" in build.headline_html(None)
    h = build.headline_html({"companies": 120, "hit10": 0.183, "hit50": 0.4, "hit10_random": 0.004})
    assert "<b>120</b>" in h and "<b>18%</b>" in h and "random order: 0%" in h and "not a guarantee" in h
    h = build.headline_html({"companies": 713, "hit10": 0.525, "hit50": 0.776, "hit10_random": 0.136, "hit10_cpv": 0.216})
    assert "<b>52%</b>" in h and "random order: 14%" in h and "CPV code alone: 22%" in h and "simpler text matcher stays" in h
