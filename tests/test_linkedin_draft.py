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
