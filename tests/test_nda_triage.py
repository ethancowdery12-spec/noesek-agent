from noesek.tools.nda_triage import NdaTriageInput as I, nda_triage as f

CLEAN = ("This Mutual Non-Disclosure Agreement is between each party. Confidential Information means non-public information marked confidential. "
         "Each party shall use reasonable care. Confidential Information excludes information that is publicly available, already known prior to disclosure, "
         "independently developed, rightfully received from a third party, or required by law to be disclosed. "
         "Obligations survive for three (3) years after termination. This Agreement is governed by the laws of the State of Delaware.")


def test_clean_mutual_nda_is_green():
    r = f(I(text=CLEAN))
    assert r["rating"] == "GREEN", r
    assert r["type"] == "mutual" and r["longest_term_years"] == 3 and r["executed"] is False


def test_non_solicit_and_non_compete_are_red_with_quotes():
    r = f(I(text=CLEAN + " The Recipient shall not solicit any employee of the Discloser. The Recipient agrees to a non-compete for two years."))
    assert r["rating"] == "RED" and {"non_solicit", "non_compete"} <= set(r["red_flags"])
    assert "solicit" in r["red_flags"]["non_solicit"][0]


def test_missing_carveouts_and_long_term_are_yellow():
    t = "This Mutual NDA covers each party. Confidential Information is any and all information disclosed. Obligations survive for 10 years. Governed by the laws of the State of Delaware."
    r = f(I(text=t, max_term_years=5))
    assert r["rating"] == "YELLOW"
    assert {"missing_carveouts", "term_over_limit", "overbroad_definition"} <= set(r["yellow_flags"])


def test_perpetual_and_residuals():
    assert "perpetual" in f(I(text=CLEAN + " Obligations are perpetual."))["yellow_flags"]
    assert f(I(text=CLEAN + " The recipient may use residuals retained in unaided memory."))["rating"] == "RED"


def test_one_way_binding_owner_as_recipient():
    t = CLEAN.replace("Mutual ", "").replace("each party", "the Company will disclose to the Recipient").replace("Each party", "The Recipient")
    r = f(I(text=t, we_are="recipient"))
    assert r["type"] == "unilateral" and "one_way_binds_us" in r["yellow_flags"]


def test_not_an_nda_and_no_term_note():
    assert f(I(text="Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do."))["ok"] is False
    r = f(I(text="Mutual NDA: each party keeps confidential information secret. It excludes publicly available info, already known info, independently developed info, info from a third party and info required by law."))
    assert any("no term" in n for n in r["notes"]) and any("governing law" in n for n in r["notes"])
