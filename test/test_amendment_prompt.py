"""Legal-amendment helper: finding a figure, the prompt, and the guard rails on the SQL a master pastes."""
from app.services import amendment_prompt as amp


def test_figure_patterns_cover_the_common_spellings():
    assert amp.figure_patterns("7500") == ["7500", "7,500", "7_500"]
    assert amp.figure_patterns(" 7,500 ") == ["7500", "7,500", "7_500"]
    assert amp.figure_patterns("18") == ["18"] and amp.figure_patterns("") == []


def test_a_figure_does_not_match_inside_a_longer_number():
    import re
    rx = re.compile(amp._regex_for(amp.figure_patterns("7500")))
    assert rx.search("COALESCE(x, 7500)") and rx.search("up to ₹7,500 a month")
    assert not rx.search("17500") and not rx.search("75000")


def test_the_prompt_carries_the_form_the_figure_and_the_rules():
    usages = {"figure": "7500", "thresholds": [{"state": "ALL", "threshold_key": "gst_per_member_monthly", "value": 7500,
              "unit": "rupees", "effective_from": "2017-07-01", "effective_to": None, "is_active": True}],
              "rules": [], "functions": [{"name": "fn_x", "lines": [{"line": 3, "text": "COALESCE(v, 7500)"}]}], "files": []}
    p = amp.build_prompt({"id": 4, "title": "Notification 12/2017-CT (Rate)", "provisions": "exempts up to 7,500",
                          "status": "active"}, {"old": "7500", "new": "10000", "effective": "2027-04-01"}, usages)
    for needle in ("Notification 12/2017-CT (Rate)", "**7500** becomes **10000**, effective **2027-04-01**",
                   "gst_per_member_monthly", "`fn_x`", "regime_rule_parameters", "ON CONFLICT (state, threshold_key, effective_from)",
                   "pg_get_functiondef", "rollback script"):
        assert needle in p, needle


def test_the_prompt_without_a_figure_asks_claude_to_say_what_it_inferred():
    p = amp.build_prompt({"title": "X"}, {}, None)
    assert "has not stated the old and new figure" in p and "did not give a figure" in p


def test_pasted_sql_guard_rails():
    ok = "UPDATE state_compliance_thresholds SET value = 10000 WHERE threshold_key = 'gst_per_member_monthly';"
    assert amp.check_sql(ok) is None
    assert "Paste" in amp.check_sql("   ")
    assert "COMMIT" in amp.check_sql(ok + "\nCOMMIT;")
    assert "AOA Rule Editor" in amp.check_sql("UPDATE regime_rule_parameters SET value = 1;")
    assert "Destructive" in amp.check_sql("DELETE FROM state_compliance_thresholds;")
    assert amp.check_sql("-- DELETE FROM x\n" + ok) is None          # a comment is not a statement
    assert amp.sql_digest(ok) == amp.sql_digest("  " + ok + "\n")     # whitespace around it does not change the digest
