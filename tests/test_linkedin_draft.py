from noesek.tools.linkedin_draft import LinkedInDraftInput as I, linkedin_draft as f, parse_url


def test_parse_url_shapes():
    r = parse_url("https://www.linkedin.com/posts/jane_x-activity-7123456789012345678-AbCd?utm=1")
    assert r["post"]["urn"] == "urn:li:activity:7123456789012345678"
    assert parse_url("https://www.linkedin.com/feed/update/urn:li:share:7000000000000000001/")["post"]["id"] == "7000000000000000001"
    assert "error" in parse_url("https://example.com/x")
    assert "error" in parse_url("https://www.linkedin.com/in/jane")


def test_lint_flags_style_problems():
    out = f(I(action="lint", kind="comment", text="Great insight! We should leverage this. What do you think?"))
    rules = {i["rule"] for i in out["issues"]}
    assert {"vocabulary", "opener", "dead-prompt", "specificity", "length-target"} <= rules


def test_lint_clean_comment():
    t = ("We cut Stripe fees from 2.9% to 0.8% by moving 40 invoices to ACH.\n\n"
         "Did you see the same drop on chargebacks after the switch to Plaid bank checks last quarter, or did disputes stay flat while fees fell for your team?")
    assert f(I(action="lint", kind="comment", text=t))["passed"] is True


def test_card_never_posts():
    out = f(I(action="card", kind="post", text="In March 2026 I shipped Noesek and 3 tests failed.",
              url="https://www.linkedin.com/feed/update/urn:li:share:7000000000000000001/"))
    assert out["status"].startswith("NOT POSTED") and out["target"]["post"]["id"]


def test_plan_and_hooks():
    assert len(f(I(action="plan_week", founder=True, topics=["a"]))["plan"]) == 5
    assert "controlled_ab_anecdote" in f(I(action="hooks"))["hooks"]
    assert "error" in f(I(action="nope"))


def test_module_has_no_network_or_post_code():
    import noesek.tools.linkedin_draft as m
    src = open(m.__file__).read()
    assert "httpx" not in src and "requests" not in src


def test_lint_length_limits_per_kind():
    assert any(i["rule"] == "length" for i in f(I(action="lint", kind="post", text="A" * 3001 + " 5"))["issues"])
    assert not any(i["rule"] == "length" for i in f(I(action="lint", kind="post", text="Shipped 5 tests " * 100))["issues"])
    assert any(i["rule"] == "length" for i in f(I(action="lint", kind="reply", text="Acme " + "x" * 1260))["issues"])


def test_lint_hashtags_by_kind():
    assert any(i["rule"] == "hashtags" for i in f(I(action="lint", kind="comment", text="Saved 40 hours #ai"))["issues"])
    six = " ".join(f"#t{i}" for i in range(6))
    assert any(i["rule"] == "hashtags" for i in f(I(action="lint", kind="post", text=f"Shipped 3 things {six}"))["issues"])
    assert not any(i["rule"] == "hashtags" for i in f(I(action="lint", kind="post", text="Shipped 3 things #ai #ml"))["issues"])


def test_lint_em_dash_density_and_hook_length():
    assert any(i["rule"] == "em-dash-density" for i in f(I(action="lint", kind="post", text="Cut 3 costs \u2014 and 4 more \u2014 today \u2014 now"))["issues"])
    assert any(i["rule"] == "hook-length" for i in f(I(action="lint", kind="post", text="Acme " + "word " * 60 + "\nsecond"))["issues"])


def test_lint_unknown_kind_and_empty_text():
    assert "error" in f(I(action="lint", kind="story", text="x 1"))
    assert f(I(action="lint", text="   "))["error"] == "text is required"
    assert "error" in f(I(action="card", text=""))


def test_parse_url_comment_ref_and_unknown_action():
    u = "https://www.linkedin.com/feed/update/urn:li:activity:7123456789012345678/?commentUrn=urn%3Ali%3Acomment%3A(activity%3A1,2)"
    r = parse_url(u)
    assert r["post"]["id"] == "7123456789012345678" and r["comment_ref"]
    assert "actions" in f(I(action="publish"))


def test_plan_week_topics_and_founder_pillars():
    g = f(I(action="plan_week", topics=["a", "b"]))["plan"]
    assert [p["topic"] for p in g[:2]] == ["a", "b"] and g[2]["topic"].startswith("(choose")
    fo = f(I(action="plan_week", founder=True))["plan"]
    assert fo[0]["pillar"] == "Conviction" and len(fo) == 5


def test_card_with_url_targets_and_stays_unposted():
    out = f(I(action="card", kind="comment", text="We cut 40 hours at Acme Corp.",
              url="https://www.linkedin.com/feed/update/urn:li:share:7000000000000000001/"))
    assert out["status"].startswith("NOT POSTED") and out["target"]["post"]["id"] == "7000000000000000001"
